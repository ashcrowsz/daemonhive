"""Records over a whole training history: PRs, regressions, bests. Pure arithmetic, tier 0.

Used by the importer (to backfill memory) and by the `ask` skill (to answer questions),
so "what's my last PR" means exactly what the backfilled HIT_PR facts mean.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from daemonhive.agents.fitness.analysis import compare, estimated_1rm, regressions
from daemonhive.agents.fitness.parser import Exercise, Session, SetEntry

MIN_PR_HISTORY = 2  # an exercise needs a couple of sessions before "best ever" means much


def session_key(s: Session) -> str:
    return f"Session:{s.kind}:{s.day.isoformat()}"


def known_load(ex: Exercise) -> Exercise:
    """Only sets with a real kg number count for comparisons ("Max", "5 plates" don't)."""
    return Exercise(ex.name, [x for x in ex.sets if x.weight_kg > 0])


def comparable(s: Session) -> Session:
    return Session(s.kind, s.day, [e for e in map(known_load, s.exercises) if e.sets], s.notes)


def best_set(ex: Exercise) -> SetEntry:
    return max(ex.sets, key=lambda x: estimated_1rm(x.weight_kg, x.reps))


def fmt_set(s: SetEntry) -> str:
    return f"{s.weight_kg:g} kg x {s.reps}"


def find_regressions(sessions: list[Session]) -> dict[date, list[dict[str, Any]]]:
    """Same rule as the live agent: vs the last session of the same kind."""
    last: dict[str, Session] = {}
    out: dict[date, list[dict[str, Any]]] = {}
    for s in sessions:
        cur = comparable(s)
        prev = last.get(s.kind)
        if prev:
            bad = regressions(compare(prev, cur))
            if bad:
                out[s.day] = [
                    {
                        "exercise": d.exercise,
                        "volume_before": d.volume_before,
                        "volume_after": d.volume_after,
                        "volume_change": round(d.volume_change, 3),
                        "previous": prev.day.isoformat(),
                    }
                    for d in bad
                ]
        last[s.kind] = cur
    return out


def find_prs(
    sessions: list[Session], marked: dict[date, list[str]] | None = None
) -> list[dict[str, Any]]:
    """Best estimated 1RM per exercise; a PR is beating every earlier session."""
    marked = marked or {}
    best: dict[str, tuple[float, str]] = {}
    seen: dict[str, int] = {}
    prs: list[dict[str, Any]] = []
    for s in sorted(sessions, key=lambda x: x.day):
        for ex in comparable(s).exercises:
            top = best_set(ex)
            e1 = estimated_1rm(top.weight_kg, top.reps)
            seen[ex.name] = seen.get(ex.name, 0) + 1
            prev = best.get(ex.name)
            is_pr = prev is not None and e1 > prev[0] * 1.005 and seen[ex.name] > MIN_PR_HISTORY
            if is_pr or ex.name in marked.get(s.day, []):
                prs.append(
                    {
                        "day": s.day,
                        "session": session_key(s),
                        "kind": s.kind,
                        "exercise": ex.name,
                        "top_set": fmt_set(top),
                        "e1rm": round(e1, 1),
                        "previous_best": round(prev[0], 1) if prev else None,
                        "previous_set": prev[1] if prev else None,
                        "marked_in_log": ex.name in marked.get(s.day, []),
                    }
                )
            if prev is None or e1 > prev[0]:
                best[ex.name] = (e1, fmt_set(top))
    return prs


def all_time_best(sessions: list[Session], exercise: str) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    heaviest: dict[str, Any] | None = None
    for s in sessions:
        ex = comparable(s).exercise(exercise)
        if not ex:
            continue
        top = best_set(ex)
        e1 = estimated_1rm(top.weight_kg, top.reps)
        if best is None or e1 > best["e1rm"]:
            best = {"day": s.day, "kind": s.kind, "set": fmt_set(top), "e1rm": round(e1, 1)}
        h = max(ex.sets, key=lambda x: (x.weight_kg, x.reps))
        if heaviest is None or h.weight_kg > heaviest["kg"]:
            heaviest = {"day": s.day, "set": fmt_set(h), "kg": h.weight_kg}
    if best is None:
        return None
    return {"exercise": exercise, "best_e1rm": best, "heaviest": heaviest}
