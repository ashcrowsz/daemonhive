"""The diary importer, on synthetic lines written in the same messy style as a real log."""

from datetime import date, timedelta

from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow, recovery_summary
from daemonhive.importer.history import assign_dates, parse_date, parse_diary, parse_sets
from daemonhive.importer.simulate import BAD_KCAL, BAD_SLEEP_H, build

DIARY = """Week 2: 20-26 October 100.5kg
23 October: Push 1
Bench Press 100kg 1 x 9
Incline Bench Press 100kg  1 x 5

25th October:
Deadlift:
Top set 180kg x1
150kg 3x3

27 October: Push 1
Bench Press 100kg 1 x 3 (Failed 4th rep)
Incline Bench Press 100kg 2 x 7 - 6
20min Incline Treadmill

Maintenance Phase Start

30 October Upper (Fasted, sub 5h poor sleep):
Latpulldown 93kg 2x8-7
Flat Press 5 Plates 1x5, 4 Plates 1x5
Triceps Pushdown Max + 12.3kg 1x7, Max 1x7
Next Lower: Squat 100kg 3x8

Upper:
Lat Pulldown 100kg 2x8 (PR)
Peck Deck Max 2x10-9

3rd November : Push 2 1800kcal
Bench Press 105kg 3x3 RPE 8
Bench Press 140kg 1x1 Fail
Incline Bench Press 100kg 2x8 (Glute sprain)
"""


def diary():
    return parse_diary(DIARY, 2025)


def test_dates_in_every_style() -> None:
    assert parse_date("March 9: Pull", 2026) == date(2026, 3, 9)
    assert parse_date("19th March Lower:", 2026) == date(2026, 3, 19)
    assert parse_date("1st November : Pull 2", 2025) == date(2025, 11, 1)
    # "November 98.5kg" is not the 98th of November: fall back to "3-9th November"
    assert parse_date("Week 4: 3-9th November 98.5kg", 2025) == date(2025, 11, 9)


def test_sets_ranges_loads_and_failures() -> None:
    s = parse_sets("Latpulldown 93kg 2x8-7")
    assert [(x.weight_kg, x.reps) for x in s] == [(93, 8), (93, 7)]
    s = parse_sets("Flat Press 5 Plates 1x5, 4 Plates 1x5")
    assert [x.load for x in s] == ["5 Plates", "4 Plates"] and s[0].weight_kg == 0
    s = parse_sets("Squat 140kg 1x1, 160kg 1x1, 180kg 1x1 RPE 10!!!!")
    assert [x.weight_kg for x in s] == [140, 160, 180] and s[-1].rpe == 10
    assert parse_sets("Bench Press 140kg 1x1 Fail") == []  # a miss is not a set
    assert [x.reps for x in parse_sets("Squat 120kg 3x3-5-5")] == [3, 5, 5]


def test_diary_sessions_notes_and_signals() -> None:
    d = diary()
    days = assign_dates(d.days, date(2025, 11, 30))
    by_day = {x.day: x for x in days}
    assert [x.day for x in days] == sorted(x.day for x in days)
    # "Deadlift:" then its sets on the next lines
    dl = by_day[date(2025, 10, 25)].exercises[0]
    assert dl.name == "deadlift" and [s.reps for s in dl.sets] == [1, 3, 3, 3]
    # the plan after "Next Lower:" is not a workout
    upper = by_day[date(2025, 10, 30)]
    assert "back squat" not in [e.name for e in upper.exercises]
    assert upper.sleep_h == 4.5 and upper.kind == "upper"
    assert by_day[date(2025, 10, 27)].notes == ["20min Incline Treadmill"]
    # an undated "Upper:" sits between its dated neighbours, marked as estimated
    est = [x for x in days if x.estimated_date]
    assert len(est) == 1 and date(2025, 10, 30) < est[0].day < date(2025, 11, 3)
    assert est[0].marked_prs == ["lat pulldown"]
    last = by_day[date(2025, 11, 3)]
    assert last.kcal == 1800 and last.injuries == ["glute sprain"]
    assert max(s.weight_kg for e in last.exercises for s in e.sets) == 105  # the failed 140 is gone
    assert d.body_weight == [(date(2025, 10, 26), 100.5)]
    assert d.phases == [(date(2025, 10, 30), "maintenance")]


def test_bad_days_get_bad_recovery_and_facts() -> None:
    d = diary()
    days = assign_dates(d.days, date(2025, 11, 30))
    bf = build(d, days, date(2025, 11, 30), kcal_target=1950)
    # 23 Oct -> 27 Oct push: bench 900 kg -> 300 kg of volume: a regression day
    bad = date(2025, 10, 27)
    assert bad in bf.regression_days
    night = {s.night_of: s.hours for s in bf.sleep}
    kcal: dict[date, int] = {}
    for m, _ in bf.meals:
        kcal[m.day] = kcal.get(m.day, 0) + m.kcal
    assert night[bad - timedelta(days=1)] == BAD_SLEEP_H
    assert abs(kcal[bad] - BAD_KCAL) <= 10 and abs(kcal[bad - timedelta(days=1)] - BAD_KCAL) <= 10
    normal = [k for day, k in kcal.items() if day not in (bad, bad - timedelta(days=1))]
    assert all(1700 <= k <= 2100 for k in normal)
    assert abs(kcal[date(2025, 11, 3)] - 1800) <= 10  # the diary's own number wins
    flags = {f.obj for f in bf.facts if f.subject == "Session:push:2025-10-27"}
    assert flags == {"SleepDeficit", "CalorieDeficit"}
    rels = {(f.agent, f.relation) for f in bf.facts}
    assert ("fitness", "AFFECTED_BY") in rels and ("wellbeing", "IN_PHASE") in rels
    assert any(f.obj == "Injury:glute sprain" for f in bf.facts)


def test_one_bad_night_is_enough_to_flag() -> None:
    until = date(2026, 1, 10)
    sleep = [SleepRow(until - timedelta(days=i), h) for i, h in ((3, 7.0), (2, 7.0), (1, 4.0))]
    meals = [MealRow(until - timedelta(days=i), k) for i, k in ((3, 1900), (2, 1900), (1, 1400))]
    rec = recovery_summary(sleep, meals, until=until, days=3, kcal_target=1950)
    assert rec["avg_sleep_h"] == 6.0  # the 3-night average alone would not flag it
    assert rec["flags"] == ["SleepDeficit", "CalorieDeficit"]
