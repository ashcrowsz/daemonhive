from datetime import date, datetime

from daemonhive.agents.scribe.hygiene import Fact, invalidate_superseded, merge_candidates, value_at
from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow, recovery_summary
from daemonhive.agents.work.planner import Busy, plan_deep_work

D = date(2026, 11, 3)


def test_recovery_flags_short_sleep_and_deficit() -> None:
    sleep = [
        SleepRow(date(2026, 10, 31), 5.0),
        SleepRow(date(2026, 11, 1), 5.5),
        SleepRow(date(2026, 11, 2), 5.0),
        SleepRow(date(2026, 10, 20), 9.0),
    ]
    meals = [
        MealRow(date(2026, 10, 31), 2200),
        MealRow(date(2026, 11, 1), 2100),
        MealRow(date(2026, 11, 2), 1300),
        MealRow(date(2026, 11, 2), 1000),
    ]
    out = recovery_summary(sleep, meals, until=D, days=3, kcal_target=2800)
    assert out["avg_sleep_h"] == 5.2 and out["nights_logged"] == 3
    assert out["kcal_vs_target"] == -600
    assert out["flags"] == ["SleepDeficit", "CalorieDeficit"]


def test_recovery_with_no_data_has_no_flags() -> None:
    out = recovery_summary([], [], until=D, days=3, kcal_target=2800)
    assert out["avg_sleep_h"] is None and out["flags"] == []


def test_deep_work_moves_after_short_night() -> None:
    normal = plan_deep_work(D, [])
    tired = plan_deep_work(D, [], short_night=True)
    assert normal and normal.start == datetime(2026, 11, 3, 8, 0)
    assert tired and tired.start == datetime(2026, 11, 3, 11, 0)


def test_deep_work_respects_meetings() -> None:
    busy = [
        Busy(datetime(2026, 11, 3, 8), datetime(2026, 11, 3, 9, 30)),
        Busy(datetime(2026, 11, 3, 10, 30), datetime(2026, 11, 3, 16)),
    ]
    block = plan_deep_work(D, busy)
    assert block and block.start == datetime(2026, 11, 3, 16, 0)
    assert plan_deep_work(D, busy, minutes=240) is None


def test_scribe_merges_spelling_variants() -> None:
    groups = merge_candidates(["Bench Press", "bench-press", "BP", "Squat", "back squat"])
    assert groups == {
        "bench press": ["BP", "Bench Press", "bench-press"],
        "back squat": ["Squat", "back squat"],
    }


def test_scribe_closes_superseded_facts_without_deleting() -> None:
    facts = [
        Fact("Person:me", "HAS_WEIGHT", "82kg", date(2026, 9, 1)),
        Fact("Person:me", "HAS_WEIGHT", "80kg", date(2026, 10, 15)),
        Fact("Session:push:2026-11-03", "AFFECTED_BY", "SleepDeficit", D),
    ]
    out = invalidate_superseded(facts)
    assert len(out) == 3
    assert value_at(out, "Person:me", "HAS_WEIGHT", date(2026, 10, 1)) == "82kg"
    assert value_at(out, "Person:me", "HAS_WEIGHT", date(2026, 11, 1)) == "80kg"
