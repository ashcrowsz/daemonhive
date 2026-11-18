"""The demo seed must actually produce the reference scenario when replayed."""

import asyncio
from datetime import date

from daemonhive.agents.concierge.routing import route_by_rules
from daemonhive.agents.wellbeing.logs import parse_log
from scenarios.harness import FakeWellbeing, run_fitness
from scenarios.seed_demo import seed_messages, todays_session

TODAY = date(2026, 11, 18)


def test_every_seed_message_routes_at_tier0() -> None:
    for text in seed_messages(TODAY):
        r = route_by_rules(text)
        assert r is not None and r.tier == 0, text


def test_seed_then_today_reproduces_the_scenario() -> None:
    msgs = seed_messages(TODAY)
    workout, logs = msgs[0], msgs[1:]
    parsed = [parse_log(m, TODAY) for m in logs]
    wb = FakeWellbeing(
        sleep=[p.sleep for p in parsed if p.sleep],
        meals=[p.meal for p in parsed if p.meal],
    )
    out, memory = asyncio.run(run_fitness([workout], todays_session(TODAY), wb))
    assert "a2a:wellbeing.recovery_summary:completed" in out.trace
    assert ("Session:push:2026-11-18", "AFFECTED_BY", "SleepDeficit") in memory.facts
    assert ("Session:push:2026-11-18", "AFFECTED_BY", "CalorieDeficit") in memory.facts
    assert "(-62%)" in out.message
