"""Work's 'plan my day' message for each answer Well-being can give (or not give)."""

import asyncio
from datetime import date

import pytest

from daemonhive.agents.work import app as work
from daemonhive.common.a2a import TaskResult, TaskState

TODAY = date(2026, 11, 18)


def plan_with(result: TaskResult, monkeypatch: pytest.MonkeyPatch) -> str:
    async def fake_send(base_url, skill, payload):
        return result

    monkeypatch.setattr(work.a2a, "send", fake_send)
    return asyncio.run(work.plan_message(TODAY))


def test_short_night_pushes_deep_work_back(monkeypatch):
    res = TaskResult(
        id="t",
        state=TaskState.completed,
        output={"nights_logged": 1, "avg_sleep_h": 5.0, "flags": ["SleepDeficit"]},
    )
    assert "Pushed back: you slept 5.0 h" in plan_with(res, monkeypatch)


def test_no_sleep_logged_assumes_fine(monkeypatch):
    res = TaskResult(id="t", state=TaskState.completed, output={"nights_logged": 0, "flags": []})
    assert "No sleep logged" in plan_with(res, monkeypatch)


def test_wellbeing_down_says_so(monkeypatch):
    res = TaskResult(id="t", state=TaskState.failed, error="connection refused")
    msg = plan_with(res, monkeypatch)
    assert "Recovery data unavailable" in msg
    assert "No sleep logged" not in msg
