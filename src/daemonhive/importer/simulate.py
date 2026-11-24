"""Backfill a year: sessions from the diary, recovery data simulated around them.

The diary has training, not sleep or food, so those are simulated with a fixed seed:
- a normal day: 1800-2000 kcal, about 7 h of sleep
- a day where Fitness flags a regression (volume -25% on a lift vs the last session of
  that kind, the same rule the live agent uses): 1400 kcal that day and the day before,
  4 h of sleep the night before
- anything the diary states wins ("1800kcal" in a header, "sub 5h poor sleep", "(5h sleep)")

Then the facts each agent would have written into memory, dated when they became true.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from daemonhive.agents.fitness.parser import Session
from daemonhive.agents.fitness.records import find_prs, find_regressions, session_key
from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow, recovery_summary
from daemonhive.importer.history import Diary, DiaryDay

NORMAL_KCAL = (1800, 2000)
NORMAL_SLEEP_H = 7.0
BAD_KCAL = 1400
BAD_SLEEP_H = 4.0
MEALS = (("breakfast", 0.25), ("lunch", 0.35), ("dinner", 0.40))


@dataclass(frozen=True)
class Fact:
    agent: str
    subject: str
    relation: str
    obj: str
    valid_from: str
    props: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass
class Backfill:
    sessions: list[Session]
    sleep: list[SleepRow]
    meals: list[tuple[MealRow, str]]
    body_weight: list[tuple[date, float]]
    facts: list[Fact]
    regression_days: list[date]
    prs: list[dict[str, Any]]


def simulate_recovery(
    days: list[DiaryDay], regression_days: set[date], start: date, end: date, seed: int = 7
) -> tuple[list[SleepRow], list[tuple[MealRow, str]]]:
    rng = random.Random(seed)
    sleep: dict[date, float] = {}
    kcal: dict[date, int] = {}
    d = start
    while d <= end:
        sleep[d] = min(7.75, max(6.25, round(rng.gauss(NORMAL_SLEEP_H, 0.35) * 4) / 4))
        kcal[d] = round(rng.randint(*NORMAL_KCAL), -1)
        d += timedelta(days=1)
    for day in regression_days:
        for k in (day - timedelta(days=1), day):
            if k in kcal:
                kcal[k] = BAD_KCAL
        if day - timedelta(days=1) in sleep:
            sleep[day - timedelta(days=1)] = BAD_SLEEP_H
    for dd in days:  # what the diary says beats the simulation
        if dd.day is None:
            continue
        if dd.kcal:
            kcal[dd.day] = dd.kcal
        if dd.sleep_h is not None:
            sleep[dd.day - timedelta(days=1)] = dd.sleep_h
    meals = [
        (MealRow(day, round(total * share, -1)), label)
        for day, total in sorted(kcal.items())
        for label, share in MEALS
    ]
    return [SleepRow(n, h) for n, h in sorted(sleep.items())], meals


def build(diary: Diary, dated: list[DiaryDay], end: date, kcal_target: int) -> Backfill:
    from daemonhive.importer.history import to_session

    sessions = [to_session(d) for d in dated]
    regs = find_regressions(sessions)
    marked = {d.day: d.marked_prs for d in dated if d.day and d.marked_prs}
    prs = find_prs(sessions, marked)
    start = sessions[0].day - timedelta(days=7)
    sleep, meals = simulate_recovery(dated, set(regs), start, end)

    facts: list[Fact] = []
    for p in prs:
        facts.append(
            Fact(
                "fitness",
                p["session"],
                "HIT_PR",
                f"Exercise:{p['exercise']}",
                p["day"].isoformat(),
                {k: v for k, v in p.items() if k not in ("day", "session")},
            )
        )
    by_day = {s.day: s for s in sessions}
    meal_rows = [m for m, _ in meals]
    for day, bad in sorted(regs.items()):
        rec = recovery_summary(sleep, meal_rows, until=day, days=3, kcal_target=kcal_target)
        for flag in rec["flags"]:  # type: ignore[union-attr]
            facts.append(
                Fact(
                    "fitness",
                    session_key(by_day[day]),
                    "AFFECTED_BY",
                    str(flag),
                    day.isoformat(),
                    {
                        "lifts": bad,
                        "avg_sleep_h": rec["avg_sleep_h"],
                        "last_night_h": rec["last_night_h"],
                        "kcal_vs_target": rec["kcal_vs_target"],
                        "kcal_yesterday": rec["kcal_yesterday"],
                    },
                )
            )
    for d in dated:
        for injury in dict.fromkeys(d.injuries):
            assert d.day is not None
            facts.append(
                Fact(
                    "fitness",
                    session_key(by_day[d.day]),
                    "AFFECTED_BY",
                    f"Injury:{injury}",
                    d.day.isoformat(),
                    {"from_log": True},
                )
            )
    for day, kg in diary.body_weight:
        facts.append(
            Fact(
                "wellbeing",
                "Person:me",
                "HAS_WEIGHT",
                f"Weight:{kg:g}kg",
                day.isoformat(),
                {"kg": kg},
            )
        )
    phases = [(sessions[0].day, "cut")] + diary.phases  # weight falling from week 1: a cut
    for day, phase in phases:
        facts.append(
            Fact(
                "wellbeing",
                "Person:me",
                "IN_PHASE",
                f"Phase:{phase}",
                day.isoformat(),
                {"from_log": day != sessions[0].day},
            )
        )
    facts.sort(key=lambda f: f.valid_from)
    return Backfill(sessions, sleep, meals, diary.body_weight, facts, sorted(regs), prs)
