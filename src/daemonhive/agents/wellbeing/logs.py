"""Sleep and meal log grammar (tier 0, no model).

    slept 5.5h                       -> last night (the night before today)
    slept 7h30                       -> same, hours + minutes
    2026-11-01 slept 5h              -> the night starting 2026-11-01
    lunch chicken rice 750 kcal      -> today
    2026-11-02 dinner pasta 900kcal  -> that day

A sleep entry is keyed by the night it *starts*, which is how recovery_summary
windows work: a session on Nov 3 looks at the nights of Oct 31, Nov 1 and Nov 2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow

DATE = r"(?:(?P<date>\d{4}-\d{2}-\d{2})\s+)?"
SLEEP = re.compile(
    DATE + r"(?:slept|sleep)\s+(?P<h>\d+(?:\.\d+)?)\s*h(?:\s*(?P<m>\d{1,2}))?\b", re.IGNORECASE
)
MEAL = re.compile(
    DATE + r"(?P<kind>breakfast|lunch|dinner|snack)\b(?P<label>.*?)(?P<kcal>\d+)\s*kcal\b",
    re.IGNORECASE,
)


class LogError(ValueError):
    pass


@dataclass(frozen=True)
class Parsed:
    sleep: SleepRow | None = None
    meal: MealRow | None = None
    label: str = ""


def is_wellbeing_log(text: str) -> bool:
    t = text.strip()
    return bool(SLEEP.match(t) or MEAL.match(t))


def parse_log(text: str, today: date) -> Parsed:
    t = text.strip()
    if m := SLEEP.match(t):
        hours = float(m["h"]) + (int(m["m"]) / 60 if m["m"] else 0)
        if not 0 < hours <= 16:
            raise LogError(f"implausible sleep: {hours:g} h")
        night = date.fromisoformat(m["date"]) if m["date"] else today - timedelta(days=1)
        return Parsed(sleep=SleepRow(night, round(hours, 2)))
    if m := MEAL.match(t):
        kcal = int(m["kcal"])
        if not 0 < kcal <= 5000:
            raise LogError(f"implausible meal: {kcal} kcal")
        day = date.fromisoformat(m["date"]) if m["date"] else today
        label = f"{m['kind'].lower()} {m['label'].strip()}".strip()
        return Parsed(meal=MealRow(day, kcal), label=label)
    raise LogError("try 'slept 6.5h' or 'lunch chicken rice 750 kcal' (optional YYYY-MM-DD first)")
