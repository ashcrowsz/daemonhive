"""Work agent's planner: place deep-work blocks around what the graph knows about you.

Step 6 of the reference scenario: after a short night (SleepDeficit fact valid
on that date), don't put a deep-work block first thing in the morning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True)
class Busy:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Block:
    start: datetime
    end: datetime
    label: str = "deep work"


DAY_START = time(8, 0)
DAY_END = time(19, 0)
SHORT_NIGHT_NOT_BEFORE = time(11, 0)


def free_slots(day: date, busy: list[Busy], not_before: time = DAY_START) -> list[tuple[datetime, datetime]]:
    cursor = datetime.combine(day, max(DAY_START, not_before))
    end_of_day = datetime.combine(day, DAY_END)
    slots: list[tuple[datetime, datetime]] = []
    for b in sorted(busy, key=lambda b: b.start):
        if b.end <= cursor:
            continue
        if b.start > cursor:
            slots.append((cursor, min(b.start, end_of_day)))
        cursor = max(cursor, b.end)
    if cursor < end_of_day:
        slots.append((cursor, end_of_day))
    return [(s, e) for s, e in slots if e > s]


def plan_deep_work(
    day: date, busy: list[Busy], *, minutes: int = 120, short_night: bool = False
) -> Block | None:
    not_before = SHORT_NIGHT_NOT_BEFORE if short_night else DAY_START
    need = timedelta(minutes=minutes)
    for start, end in free_slots(day, busy, not_before):
        if end - start >= need:
            return Block(start, start + need)
    return None
