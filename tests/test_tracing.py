"""LangSmith tracing: off by default, one trace across the A2A hop when on. No network:
the LangSmith client is a mock, and we look at the run tree from inside the spans."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from langsmith import Client, tracing_context
from langsmith.run_helpers import get_current_run_tree

from daemonhive.common.agentic import Tool, run_agent
from daemonhive.common.tiers import Tier
from daemonhive.common.tracing import continue_trace, trace_headers, traceable


@pytest.fixture
def tracing_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    client = MagicMock(spec=Client)
    # runs rebuilt from trace headers pick the default client: keep those offline too
    monkeypatch.setattr("langsmith.run_trees.get_cached_client", lambda **_: client)
    with tracing_context(enabled=True, client=client):
        yield


def test_off_by_default_sends_no_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    assert trace_headers() == {}


def test_a2a_hop_continues_the_callers_trace(tracing_on: Any) -> None:
    seen: dict[str, Any] = {}

    @traceable(name="concierge.message")
    async def caller() -> dict[str, str]:
        run = get_current_run_tree()
        seen["caller"] = (run.trace_id, run.id)
        return trace_headers()

    headers = asyncio.run(caller())
    assert "langsmith-trace" in headers

    @traceable(name="fitness.ask")
    async def callee() -> None:
        run = get_current_run_tree()
        seen["callee"] = (run.trace_id, run.parent_run_id)

    with continue_trace(headers):  # what the A2A server does with the request headers
        asyncio.run(callee())

    trace_id, caller_id = seen["caller"]
    assert seen["callee"] == (trace_id, caller_id)


class OneToolThenAnswer:
    def __init__(self) -> None:
        self.calls = 0
        self.loop_span: tuple[str, Any] = ("", None)

    async def ask(
        self, system: str, user: str, tier: Tier = Tier.large, max_tokens: int = 600
    ) -> str:
        run = get_current_run_tree()  # the model is called from inside the loop's span
        self.loop_span = (run.name, run.id)
        self.calls += 1
        return '{"tool": "best", "args": {}}' if self.calls == 1 else '{"answer": "140 kg"}'


def test_tool_calls_are_child_spans_of_the_loop(tracing_on: Any) -> None:
    spans: list[tuple[str, Any]] = []

    async def best() -> dict[str, int]:
        run = get_current_run_tree()
        spans.append((run.name, run.parent_run_id))
        return {"kg": 140}

    model = OneToolThenAnswer()
    tools = [Tool("best", "heaviest set", {}, best)]
    run = asyncio.run(run_agent("best squat?", tools, model, "2026-11-25"))
    assert run.answer == "140 kg"
    loop_name, loop_id = model.loop_span
    assert loop_name == "agentic_retrieval"
    assert spans == [("best", loop_id)]  # the tool got its own span, under the loop
