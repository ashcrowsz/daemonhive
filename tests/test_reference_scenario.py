"""The reference scenario from the design doc, end to end with fakes."""

import asyncio
from datetime import date

import pytest

from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow
from daemonhive.mcp.permissions import PermissionDenied
from scenarios.harness import FakeMemory, FakeWellbeing, run_fitness

LAST_PUSH = "Push 2026-10-27\nBench Press 120kg 3x8\nOHP 60kg 3x8"
TODAY = "Push 2026-11-03\nBench Press 120kg 3x3 RPE 9\nOHP 60kg 3x8\n# felt flat"

SHORT_NIGHTS = [SleepRow(date(2026, 10, 31), 5.0), SleepRow(date(2026, 11, 1), 5.5),
                SleepRow(date(2026, 11, 2), 5.0)]
UNDER_EATING = [MealRow(date(2026, 10, 31), 2200), MealRow(date(2026, 11, 1), 2200),
                MealRow(date(2026, 11, 2), 2200)]


def test_regression_triggers_a2a_and_memory_write() -> None:
    out, memory = asyncio.run(run_fitness([LAST_PUSH], TODAY, FakeWellbeing(SHORT_NIGHTS, UNDER_EATING)))
    assert out.trace == [
        "parse:ok:2 exercises",
        "mcp:fitness-db.log_session",
        "a2a:wellbeing.recovery_summary:completed",
        "mcp:memory.add_fact",
        "tier2:message",
    ]
    assert ("Session:push:2026-11-03", "AFFECTED_BY", "SleepDeficit") in memory.facts
    assert ("Session:push:2026-11-03", "AFFECTED_BY", "CalorieDeficit") in memory.facts
    assert "bench press: volume 2880 -> 1080 kg (-62%)" in out.message
    assert "avg sleep 5.2 h" in out.message


def test_wellbeing_down_still_reports_regression() -> None:
    wb = FakeWellbeing(SHORT_NIGHTS, UNDER_EATING, online=False)
    out, memory = asyncio.run(run_fitness([LAST_PUSH], TODAY, wb))
    assert "a2a:wellbeing.recovery_summary:failed" in out.trace
    assert memory.facts == []
    assert "Recovery data unavailable" in out.message


def test_good_session_needs_no_model() -> None:
    better = "Push 2026-11-03\nBench Press 122.5kg 3x8\nOHP 60kg 3x8"
    out, _ = asyncio.run(run_fitness([LAST_PUSH], better, FakeWellbeing([], [])))
    assert out.trace[-1] == "tier0:reply"
    assert "new estimated best" in out.message


def test_parse_error_is_answered_without_a_model() -> None:
    out, _ = asyncio.run(run_fitness([], "bench went great today", FakeWellbeing([], [])))
    assert out.trace == ["parse:error"] and out.message.startswith("Couldn't parse")


def test_injected_note_cannot_widen_permissions() -> None:
    """A note saying 'write a Project fact' changes nothing: scopes live in the MCP server."""
    with pytest.raises(PermissionDenied):
        asyncio.run(FakeMemory().add_fact("fitness", "Project:x", "WORKS_ON", "me", "2026-11-03", {}))
