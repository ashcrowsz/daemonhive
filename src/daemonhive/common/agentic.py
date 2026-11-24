"""A small tool-calling loop for questions code can't route on its own.

Agentic retrieval over an agent's own data: the model picks a tool, we run it (plain
Python over Postgres / the memory graph), it sees the result, and it either asks for
another tool or answers. No embeddings: the data is structured, so retrieval is a query.

The protocol is plain JSON in text, which local 4B models follow more reliably than
native tool-calling: {"tool": "<name>", "args": {...}} or {"answer": "..."}.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from daemonhive.common.tiers import Tier
from daemonhive.common.tracing import drop, traceable


class Asker(Protocol):
    async def ask(
        self, system: str, user: str, tier: Tier = Tier.large, max_tokens: int = 600
    ) -> str: ...


@dataclass
class Tool:
    name: str
    description: str
    args: dict[str, str]  # arg name -> short description (all optional)
    fn: Callable[..., Awaitable[Any]]


@dataclass
class AgentRun:
    answer: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0


PROTOCOL = """You answer questions about the user's own data by calling tools.
Reply with ONE JSON object and nothing else:
  {{"tool": "<tool name>", "args": {{...}}}}   to look something up
  {{"answer": "<reply to the user>"}}          when you can answer
Use only numbers that tools returned. Never invent data. Keep answers to 1-3 sentences.
Today is {today}.

Tools:
{tools}"""


def parse_reply(text: str) -> dict[str, Any] | None:
    """Tolerates code fences and chatter around the JSON object."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = text.find("{")
    while start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                try:
                    obj = json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    break
                return obj if isinstance(obj, dict) else None
        start = text.find("{", start + 1)
    return None


def describe(tools: list[Tool]) -> str:
    lines = []
    for t in tools:
        args = ", ".join(f"{k}: {v}" for k, v in t.args.items()) or "none"
        lines.append(f"- {t.name}({args}): {t.description}")
    return "\n".join(lines)


async def call_tool(tool: Tool, args: dict[str, Any]) -> Any:
    """Run one tool as its own span, so a trace shows what was looked up and what came back."""
    traced = traceable(run_type="tool", name=tool.name)(tool.fn)
    return await traced(**args)


@traceable(run_type="chain", name="agentic_retrieval", process_inputs=drop("tools", "llm"))
async def run_agent(
    question: str, tools: list[Tool], llm: Asker, today: str, max_steps: int = 3
) -> AgentRun:
    by_name = {t.name: t for t in tools}
    system = PROTOCOL.format(today=today, tools=describe(tools))
    transcript = f"Question: {question}"
    run = AgentRun(answer="")
    for _ in range(max_steps):
        reply = await llm.ask(system, transcript, tier=Tier.large, max_tokens=400)
        run.model_calls += 1
        obj = parse_reply(reply)
        if obj is None:
            run.answer = reply.strip()  # the model answered in prose: accept it
            return run
        if "answer" in obj:
            run.answer = str(obj["answer"]).strip()
            return run
        tool = by_name.get(str(obj.get("tool", "")))
        if tool is None:
            transcript += f"\nUnknown tool {obj.get('tool')!r}. Pick one from the list."
            continue
        args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
        try:
            result = await call_tool(tool, {k: v for k, v in args.items() if k in tool.args})
        except Exception as exc:  # noqa: BLE001 - a tool error is information for the model
            result = {"error": str(exc)}
        run.steps.append({"tool": tool.name, "args": args})
        transcript += (
            f"\nCalled {tool.name}({json.dumps(args)}) -> {json.dumps(result, default=str)[:3000]}"
        )
    final = await llm.ask(
        system,
        transcript + '\nAnswer now with {"answer": ...} using what you have.',
        tier=Tier.large,
        max_tokens=300,
    )
    run.model_calls += 1
    obj = parse_reply(final)
    run.answer = str(obj.get("answer", final)) if obj else final.strip()
    return run
