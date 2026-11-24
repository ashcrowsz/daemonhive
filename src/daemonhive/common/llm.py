"""Per-agent LLM access through the LiteLLM proxy (one virtual key + budget per agent)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from daemonhive.common.tiers import TIER_MODELS, Tier
from daemonhive.common.tracing import drop, traceable


@traceable(run_type="llm", name="chat_completion", process_inputs=drop("base_url", "key"))
async def chat_completion(base_url: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    """One OpenAI-style call to LiteLLM. Traced as an LLM run (messages, tokens, model)."""
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data


class AgentLLM:
    def __init__(self, agent: str, base_url: str | None = None) -> None:
        self.agent = agent
        self.base_url = (
            base_url or os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
        ).rstrip("/")
        # per-agent virtual key (needs LiteLLM's key DB); otherwise the proxy master key
        self.key = os.environ.get(f"LITELLM_KEY_{agent.upper()}") or os.environ.get(
            "LITELLM_MASTER_KEY", "sk-local-dev"
        )
        # "none" skips thinking tokens on local reasoning models (gemma 4, qwen 3)
        self.reasoning_effort = os.environ.get("HIVE_REASONING_EFFORT", "")

    async def ask(
        self, system: str, user: str, tier: Tier = Tier.large, max_tokens: int = 600
    ) -> str:
        if tier == Tier.code:
            raise ValueError("tier 0 is code, not a model call")
        body: dict[str, Any] = {
            "model": TIER_MODELS[tier],
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "metadata": {"agent": self.agent, "tier": int(tier)},
        }
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        data = await chat_completion(
            self.base_url,
            self.key,
            body,
            langsmith_extra={
                "metadata": {
                    "agent": self.agent,
                    "tier": int(tier),
                    "ls_provider": "litellm",
                    "ls_model_name": TIER_MODELS[tier],
                }
            },
        )
        return str(data["choices"][0]["message"]["content"]).strip()
