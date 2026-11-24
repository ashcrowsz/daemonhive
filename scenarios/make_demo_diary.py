"""Write a made-up year of training in the messy style of a real notes-app diary.

    python -m scenarios.make_demo_diary > scenarios/demo-diary.txt

Used for the README screenshots and as a sample input for the importer, so nobody's real
log has to be public. Deterministic: same seed, same diary.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

START = date(2025, 11, 3)
WEEKS = 52
# (name as typed, start kg, weekly gain kg, reps)
PUSH = [
    ("Bench Press", 95, 0.6, 5),
    ("Incline Bench Press", 80, 0.45, 8),
    ("Peck Deck", None, 0, 10),
    ("Machine Lateral Raises", 40, 0.25, 10),
    ("Tri Pushdown", None, 0, 8),
]
PULL = [
    ("Latpulldown", 75, 0.45, 8),
    ("Upper Back Row", 90, 0.5, 8),
    ("Rear Delt Flye", 55, 0.2, 10),
    ("Preacher Curl", 30, 0.2, 8),
    ("DB Hammer Curl", 18, 0.1, 10),
]
LOWER = [
    ("Squat", 120, 0.8, 5),
    ("SLDL", 110, 0.7, 6),
    ("Leg Extension", 60, 0.4, 10),
    ("Seated Leg Curl", 55, 0.35, 8),
    ("Calf Raise", 50, 0.3, 10),
]
DEADLIFT = [("Deadlift", 160, 0.9, 3)]
MONTH = "January February March April May June July August September October November December"
MONTHS = MONTH.split()


def fmt_day(d: date, style: int) -> str:
    sfx = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return [
        f"{MONTHS[d.month - 1]} {d.day}",
        f"{d.day}{sfx} {MONTHS[d.month - 1]}",
        f"{d.day} {MONTHS[d.month - 1]}",
    ][style]


def line(
    rng: random.Random, name: str, base: float | None, gain: float, reps: int, week: int, bad: bool
) -> str:
    if base is None:
        extra = rng.choice(["", " + 5kg", " + 10kg"])
        return f"{name} Max{extra} 2x{reps}-{reps - rng.randint(1, 3)}"
    kg = round((base + gain * week) / 2.5) * 2.5
    if bad:
        return f"{name} {kg - 10:g}kg 1x{max(2, reps - 3)}"
    r2 = reps - rng.randint(0, 2)
    rpe = f" RPE {rng.choice([8, 8.5, 9])}" if name in ("Squat", "Bench Press", "Deadlift") else ""
    if rng.random() < 0.2:
        return f"{name} {kg + 5:g}kg 1x{max(1, reps - 2)}, {kg:g}kg 1x{reps}{rpe}"
    return f"{name} {kg:g}kg 2x{reps}-{r2}{rpe}"


def main() -> None:
    rng = random.Random(42)
    out = ["Note: made-up training diary for the daemonhive demo. Not a real person's log.", ""]
    split = [
        ("Push", PUSH),
        ("Pull", PULL + DEADLIFT[:0]),
        ("Lower", LOWER),
        ("Push", PUSH),
        ("Pull", PULL),
        ("Lower", DEADLIFT + LOWER[1:]),
    ]
    d = START
    for week in range(WEEKS):
        if week == 7:
            out += ["Cut Phase Start", ""]
        if week == 33:
            out += ["Maintenance Phase Start", ""]
        if 28 <= week < 30:  # two weeks off
            d += timedelta(days=7)
            continue
        days = sorted(rng.sample(range(7), rng.choice([3, 4, 4, 5])))
        for i, offset in enumerate(days):
            kind, lifts = split[(week * 4 + i) % len(split)]
            day = d + timedelta(days=offset)
            bad = rng.random() < 0.12
            header = f"{fmt_day(day, rng.randrange(3))}: {kind}"
            if bad and rng.random() < 0.5:
                header += " (felt flat)"
            if week in (12, 13) and rng.random() < 0.4:
                header += " 1800kcal"
            out.append(header)
            chosen = lifts[: rng.choice([3, 4, 5])]
            for name, base, gain, reps in chosen:
                out.append(line(rng, name, base, gain, reps, week, bad and name == chosen[0][0]))
            if rng.random() < 0.3:
                out.append(f"{rng.choice([20, 30, 35])}min Incline Treadmill")
            if week == 20 and i == 0:
                out.append("Lat Pulldown 90kg 1x6 (Biceps Strain?)")
            out.append("")
        d += timedelta(days=7)
    print("\n".join(out))


if __name__ == "__main__":
    main()
