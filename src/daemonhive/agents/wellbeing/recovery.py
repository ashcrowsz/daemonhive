"""Recovery summary: what Well-being shares with other agents.

Other agents get aggregates and flags, never raw meal or sleep rows.
That boundary is the reason this is an A2A skill and not a shared table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

SHORT_SLEEP_H = 6.0  # 3-night average
DEFICIT_KCAL = -400  # daily average vs target
# one bad night or one very low day is enough on its own
ACUTE_SLEEP_H = 5.0
ACUTE_DEFICIT_KCAL = -500


@dataclass(frozen=True)
class SleepRow:
    night_of: date
    hours: float


@dataclass(frozen=True)
class MealRow:
    day: date
    kcal: int


def recovery_summary(
    sleep: list[SleepRow], meals: list[MealRow], *, until: date, days: int, kcal_target: int
) -> dict[str, object]:
    start = until - timedelta(days=days)
    window_sleep = [s.hours for s in sleep if start <= s.night_of < until]
    per_day: dict[date, int] = {}
    for m in meals:
        if start <= m.day < until:
            per_day[m.day] = per_day.get(m.day, 0) + m.kcal

    avg_sleep = round(sum(window_sleep) / len(window_sleep), 1) if window_sleep else None
    kcal_delta = round(sum(per_day.values()) / len(per_day)) - kcal_target if per_day else 0

    eve = until - timedelta(days=1)
    last_night = next((s.hours for s in sleep if s.night_of == eve), None)
    yesterday = per_day.get(eve)

    flags: list[str] = []
    if (avg_sleep is not None and avg_sleep < SHORT_SLEEP_H) or (
        last_night is not None and last_night < ACUTE_SLEEP_H
    ):
        flags.append("SleepDeficit")
    if (per_day and kcal_delta <= DEFICIT_KCAL) or (
        yesterday is not None and yesterday - kcal_target <= ACUTE_DEFICIT_KCAL
    ):
        flags.append("CalorieDeficit")

    return {
        "window": f"{start.isoformat()}..{until.isoformat()}",
        "avg_sleep_h": avg_sleep,
        "nights_logged": len(window_sleep),
        "kcal_vs_target": kcal_delta,
        "days_logged": len(per_day),
        "last_night_h": last_night,
        "kcal_yesterday": yesterday,
        "flags": flags,
    }
