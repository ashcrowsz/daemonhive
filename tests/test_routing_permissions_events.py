import asyncio

import pytest

from daemonhive.agents.concierge.routing import parse_router_answer, route_by_rules
from daemonhive.common.events import Event, SeenSet, handle_once
from daemonhive.common.tiers import Tier, TierLedger
from daemonhive.mcp.permissions import Guard, PermissionDenied


@pytest.mark.parametrize(
    ("text", "agent"),
    [
        ("Push 2026-11-03\nBench Press 120kg 3x3 RPE 7", "fitness"),
        ("slept 5.5h, woke up twice", "wellbeing"),
        ("lunch chicken rice 750 kcal", "wellbeing"),
        ("move my deadline for the report to friday", "work"),
    ],
)
def test_rules_route_obvious_messages_at_tier0(text: str, agent: str) -> None:
    r = route_by_rules(text)
    assert r is not None and r.agents == (agent,) and r.tier is Tier.code


def test_ambiguous_messages_fall_through_to_a_model() -> None:
    assert route_by_rules("how am I doing lately?") is None
    assert route_by_rules("skip gym, meeting ran late and I slept badly") is None


def test_router_answer_parsing() -> None:
    assert parse_router_answer("fitness, wellbeing") == ("fitness", "wellbeing")
    assert parse_router_answer("none") == ()


def test_fitness_can_link_session_to_sleep_deficit() -> None:
    g = Guard()
    g.check_write("fitness", "Session:push:2026-11-03", "AFFECTED_BY", "SleepDeficit")
    assert g.log[-1]["allowed"] is True


def test_fitness_cannot_write_projects_or_read_habits() -> None:
    g = Guard()
    with pytest.raises(PermissionDenied):
        g.check_write("fitness", "Project:thesis", "WORKS_ON", "Person:me")
    with pytest.raises(PermissionDenied):
        g.check_read("fitness", "Habit")
    assert [e["allowed"] for e in g.log] == [False, False]


def test_unknown_agent_is_denied() -> None:
    with pytest.raises(PermissionDenied):
        Guard().check_read("intruder", "Session")


def test_idempotent_consumer() -> None:
    seen, calls, dlq = SeenSet(), [], []
    ev = Event(
        id="workout:2026-11-03:push", subject="hive.workout.logged", source="fitness", data={}
    )

    async def ok(e: Event) -> None:
        calls.append(e.id)

    async def boom(e: Event) -> None:
        raise RuntimeError("db down")

    async def dead(e: Event, err: str) -> None:
        dlq.append((e.id, err))

    run = lambda h, a=1: asyncio.run(
        handle_once(ev, seen, h, max_attempts=3, attempt=a, dead_letter=dead)
    )
    assert run(ok) == "ok"
    assert run(ok) == "duplicate" and calls == [ev.id]

    seen2 = SeenSet()
    r1 = asyncio.run(handle_once(ev, seen2, boom, max_attempts=2, attempt=1, dead_letter=dead))
    r2 = asyncio.run(handle_once(ev, seen2, boom, max_attempts=2, attempt=2, dead_letter=dead))
    assert (r1, r2) == ("retry", "dead_lettered") and dlq == [(ev.id, "db down")]


def test_tier_ledger_share() -> None:
    led = TierLedger()
    for t in (Tier.code, Tier.code, Tier.code, Tier.large):
        led.record(t)
    assert led.share(Tier.code) == 0.75
