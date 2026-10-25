"""Workout log grammar. Tier 0: no model call needed for any of this.

A log looks like what you'd type between sets:

    Push 2026-11-03
    Bench Press 120kg 3x3 RPE 7
    Incline DB Press 32.5kg 3x10 @8
    Dips BW+20kg 4x8
    OHP 60kg 5,5,4
    # felt flat today

Supported per line: <exercise> <weight><unit> <sets>x<reps> | <reps,reps,...> [RPE n | @n]
Weight: 120kg, 265lb, BW, BW+20kg. Lines starting with '#' are notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

LB_TO_KG = 0.45359237

HEADER = re.compile(r"^(?P<kind>[A-Za-z][A-Za-z ]*?)\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$")
LINE = re.compile(
    r"""^(?P<name>[A-Za-z][A-Za-z .'-]*?)\s+
        (?P<weight>BW(?:\+\d+(?:\.\d+)?(?:kg|lb))?|\d+(?:\.\d+)?(?:kg|lb))\s+
        (?:(?P<sets>\d+)\s*x\s*(?P<reps>\d+)|(?P<replist>\d+(?:\s*,\s*\d+)+))
        (?:\s+(?:RPE\s*|@)(?P<rpe>\d+(?:\.\d+)?))?\s*$""",
    re.X | re.I,
)

ALIASES = {
    "bench": "bench press",
    "bp": "bench press",
    "ohp": "overhead press",
    "squat": "back squat",
    "dl": "deadlift",
    "db": "dumbbell",
}


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class SetEntry:
    weight_kg: float
    reps: int
    rpe: float | None = None
    bodyweight: bool = False


@dataclass
class Exercise:
    name: str
    sets: list[SetEntry]

    @property
    def volume_kg(self) -> float:
        return sum(s.weight_kg * s.reps for s in self.sets)

    @property
    def top_set(self) -> SetEntry:
        return max(self.sets, key=lambda s: (s.weight_kg, s.reps))


@dataclass
class Session:
    kind: str
    day: date
    exercises: list[Exercise] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def exercise(self, name: str) -> Exercise | None:
        return next((e for e in self.exercises if e.name == name), None)


def normalize_name(raw: str) -> str:
    words = raw.lower().replace(".", "").split()
    out: list[str] = []
    for w in words:
        out.extend(ALIASES.get(w, w).split())
    return " ".join(out)


def parse_weight(token: str) -> tuple[float, bool]:
    t = token.lower()
    if t.startswith("bw"):
        extra = t[3:] if len(t) > 2 else ""
        return (parse_weight(extra)[0] if extra else 0.0), True
    value = float(t[:-2])
    return (round(value * LB_TO_KG, 2) if t.endswith("lb") else value), False


def parse_line(line: str) -> Exercise:
    m = LINE.match(line.strip())
    if not m:
        raise ParseError(f"can't read: {line!r}")
    weight, bw = parse_weight(m["weight"])
    rpe = float(m["rpe"]) if m["rpe"] else None
    if m["sets"]:
        reps = [int(m["reps"])] * int(m["sets"])
    else:
        reps = [int(r) for r in m["replist"].split(",")]
    if not reps or any(r <= 0 for r in reps) or len(reps) > 20:
        raise ParseError(f"implausible sets/reps: {line!r}")
    return Exercise(normalize_name(m["name"]), [SetEntry(weight, r, rpe, bw) for r in reps])


def parse_session(text: str) -> Session:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        raise ParseError("empty log")
    head = HEADER.match(lines[0])
    if not head:
        raise ParseError("first line must be '<Type> YYYY-MM-DD', e.g. 'Push 2026-11-03'")
    session = Session(kind=head["kind"].strip().lower(), day=date.fromisoformat(head["date"]))
    for ln in lines[1:]:
        if ln.startswith("#"):
            session.notes.append(ln.lstrip("# ").strip())
            continue
        ex = parse_line(ln)
        existing = session.exercise(ex.name)
        if existing:
            existing.sets.extend(ex.sets)
        else:
            session.exercises.append(ex)
    if not session.exercises:
        raise ParseError("no exercises found")
    return session
