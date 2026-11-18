"""Per-agent LLM access through the LiteLLM proxy (one virtual key + budget per agent)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from daemonhive.common.tiers import TIER_MODELS, Tier


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
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json=body,
            )
            r.raise_for_status()
            return str(r.json()["choices"][0]["message"]["content"]).strip()
