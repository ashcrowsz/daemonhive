"""Optional LangSmith tracing for the whole hive.

Off unless LANGSMITH_TRACING=true (plus LANGSMITH_API_KEY). When on, one question becomes
one trace across services: concierge -> A2A hop -> the owning agent -> tier-0 tool or the
agentic loop -> each tool call -> each model call. The A2A client forwards LangSmith's
trace headers and the A2A server continues the trace, so the agents don't need to know.

Traces leave the machine. The hive holds health data, so read the README's privacy note
before turning this on (LANGSMITH_HIDE_INPUTS / LANGSMITH_HIDE_OUTPUTS keep the shape and
timings but drop the content).
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from langsmith import traceable, tracing_context
from langsmith.run_helpers import get_current_run_tree

__all__ = ["continue_trace", "drop", "enabled", "trace_headers", "traceable"]

TRACE_HEADER = "langsmith-trace"


def enabled() -> bool:
    flag = os.environ.get("LANGSMITH_TRACING") or os.environ.get("LANGCHAIN_TRACING_V2", "")
    return flag.strip().lower() == "true"


def trace_headers() -> dict[str, str]:
    """Headers that let the next service attach its spans under the current one."""
    if not enabled():
        return {}
    run = get_current_run_tree()
    return dict(run.to_headers()) if run is not None else {}


@contextmanager
def continue_trace(headers: Mapping[str, str]) -> Iterator[None]:
    """Continue a caller's trace if its headers carry one; otherwise start fresh."""
    lowered = {k.lower(): v for k, v in headers.items()}
    if enabled() and TRACE_HEADER in lowered:
        with tracing_context(parent=lowered):
            yield
    else:
        yield


def drop(*names: str) -> Any:
    """process_inputs hook: keep secrets and big objects out of a span's inputs."""

    def _drop(inputs: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in inputs.items() if k not in names}

    return _drop
