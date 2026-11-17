"""Compare a session with the previous one of the same type. Pure arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from daemonhive.agents.fitness.parser import Session

REGRESSION_THRESHOLD = 0.25  # >25% volume drop on a lift is worth asking about


class Signal(str, Enum):
    pr = "pr"
    regression = "regression"
    steady = "steady"
    new = "new"


@dataclass
class LiftDelta:
    exercise: str
    signal: Signal
    volume_before: float
    volume_after: float
    top_before: float | None
    top_after: float

    @property
    def volume_change(self) -> float:
        if not self.volume_before:
            return 0.0
        return (self.volume_after - self.volume_before) / self.volume_before


def estimated_1rm(weight: float, reps: int) -> float:
    """Epley. Good enough to compare sessions, not to program from."""
    return weight if reps == 1 else weight * (1 + reps / 30)


def compare(previous: Session | None, current: Session) -> list[LiftDelta]:
    deltas: list[LiftDelta] = []
    for ex in current.exercises:
        before = previous.exercise(ex.name) if previous else None
        top = ex.top_set
        if before is None:
            deltas.append(LiftDelta(ex.name, Signal.new, 0, ex.volume_kg, None, top.weight_kg))
            continue
        e1_now = estimated_1rm(top.weight_kg, top.reps)
        e1_before = estimated_1rm(before.top_set.weight_kg, before.top_set.reps)
        delta = LiftDelta(
            ex.name,
            Signal.steady,
            before.volume_kg,
            ex.volume_kg,
            before.top_set.weight_kg,
            top.weight_kg,
        )
        if e1_now > e1_before * 1.005:
            delta.signal = Signal.pr
        elif delta.volume_change <= -REGRESSION_THRESHOLD:
            delta.signal = Signal.regression
        deltas.append(delta)
    return deltas


def regressions(deltas: list[LiftDelta]) -> list[LiftDelta]:
    return [d for d in deltas if d.signal is Signal.regression]


def describe(d: LiftDelta) -> str:
    pct = round(abs(d.volume_change) * 100)
    if d.signal is Signal.regression:
        return f"{d.exercise.title()} volume dropped {pct}%"
    if d.signal is Signal.pr:
        return f"{d.exercise.title()}: new estimated best at {d.top_after:g} kg"
    return f"{d.exercise.title()}: steady"
