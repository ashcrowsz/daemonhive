"""Answer questions about your own training: "what's my last PR?", "what did I do last push?".

Two levels, same as the rest of the hive:
- tier 0: common questions are recognised by pattern and answered from the data by code
- tier 2: anything else goes to a small tool-calling loop (common.agentic) over the same
  tools, so the model only ever sees numbers the code looked up
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from daemonhive.agents.fitness.analysis import estimated_1rm
from daemonhive.agents.fitness.parser import NAME_ALIASES, Exercise, Session, normalize_name
from daemonhive.agents.fitness.records import (
    all_time_best,
    best_set,
    comparable,
    find_prs,
    find_regressions,
    session_key,
)
from daemonhive.common.agentic import Asker, Tool, run_agent
from daemonhive.common.tiers import Tier

MemorySearch = Callable[[str], Awaitable[list[dict[str, Any]]]]

KIND_WORDS = {
    "push": "push",
    "pull": "pull",
    "upper": "upper",
    "lower": "lower",
    "legs": "lower",
    "leg day": "lower",
    "leg": "lower",
    "full body": "full body",
    "arms": "arms",
    "deadlift day": "deadlift",
}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

WHY = re.compile(r"\bwhy\b|\bwhat happened\b|\bexplain\b", re.IGNORECASE)
LAST_PR = re.compile(
    r"\b(last|latest|most recent|newest|recent)\b.*\b(prs?|records?|personal bests?)\b"
    r"|\b(prs?)\b.*\b(last|latest|recent)\b",
    re.IGNORECASE,
)
COUNT = re.compile(r"\bhow (many|often)\b", re.IGNORECASE)
FREE_WEIGHTS = re.compile(
    r"\b(bench press|squat|deadlift|overhead press|military press|pendlay row|barbell|dumbbell|"
    r"close grip bench|dips|pullup|chin up)\b"
)
IMPROVED = re.compile(
    r"\b(improved|improving|gained|biggest gains?|most progress|progressed)\b", re.IGNORECASE
)
PROGRESS = re.compile(r"\b(progress\w*|trend|improv\w*|going)\b", re.IGNORECASE)
LAST_TIME = re.compile(r"\bwhen\b.*\blast\b|\blast time\b|\bwhen did i\b", re.IGNORECASE)
BEST = re.compile(r"\b(best|max|heaviest|strongest|1rm|one rep max|prs?)\b", re.IGNORECASE)
LAST_SESSION = re.compile(r"\b(last|latest|previous|most recent)\b", re.IGNORECASE)


def nice(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b %Y}"


def describe_sets(ex: Exercise) -> str:
    groups: list[tuple[str, list[int], list[float]]] = []
    for s in ex.sets:
        label = f"{s.weight_kg:g} kg" if s.weight_kg > 0 else (s.load or "no load noted")
        if groups and groups[-1][0] == label:
            groups[-1][1].append(s.reps)
        else:
            groups.append((label, [s.reps], []))
        if s.rpe:
            groups[-1][2].append(s.rpe)
    parts = []
    for label, reps, rpe in groups:
        txt = (
            f"{len(reps)}x{reps[0]} @ {label}"
            if len(set(reps)) == 1
            else f"{label} x {', '.join(map(str, reps))}"
        )
        if rpe:
            txt += f" (RPE {max(rpe):g})"
        parts.append(txt)
    return "; ".join(parts)


def session_text(s: Session) -> str:
    lines = [
        f"{s.kind.title()} on {nice(s.day)}"
        + (" (date estimated)" if "date estimated" in s.notes else "")
        + ":"
    ]
    lines += [f"- {e.name}: {describe_sets(e)}" for e in s.exercises]
    extra = [n for n in s.notes if n != "date estimated"]
    if extra:
        lines.append("Notes: " + "; ".join(extra))
    return "\n".join(lines)


@dataclass
class Answer:
    text: str
    tier: Tier
    tool: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)


class FitnessQA:
    def __init__(
        self, sessions: list[Session], today: date, memory_search: MemorySearch | None = None
    ) -> None:
        self.sessions = sorted(sessions, key=lambda s: s.day)
        self.today = today
        self.memory_search = memory_search
        self.names = sorted({e.name for s in self.sessions for e in s.exercises})

    # ---------------- lookups (also the tools the model may call) ----------------

    def resolve_exercise(self, text: str) -> str | None:
        """Longest exercise name or alias mentioned in `text`."""
        q = " " + re.sub(r"[^a-z0-9 -]", " ", text.lower()) + " "
        q = re.sub(r"\b(squats|deadlifts|benches)\b", lambda m: m[1][:-1].rstrip("e"), q)
        candidates: list[tuple[int, str]] = []
        for name in self.names:
            if f" {name} " in q:
                candidates.append((len(name), name))
        for alias, name in NAME_ALIASES.items():
            if f" {alias} " in q and name in self.names:
                candidates.append((len(alias), name))
        if not candidates:
            n = normalize_name(text)
            return n if n in self.names else None
        return max(candidates)[1]

    async def last_session(self, kind: str | None = None) -> dict[str, Any]:
        kind = KIND_WORDS.get((kind or "").lower(), kind or None)
        pool = [s for s in self.sessions if kind is None or s.kind == kind]
        if not pool:
            return {"error": f"no {kind or ''} session logged".replace("  ", " ")}
        s = pool[-1]
        return {"session": session_key(s), "text": session_text(s), "day": s.day.isoformat()}

    async def last_pr(self, exercise: str | None = None) -> dict[str, Any]:
        prs = find_prs(self.sessions)
        if exercise:
            name = self.resolve_exercise(exercise) or exercise
            prs = [p for p in prs if p["exercise"] == name]
        if not prs:
            return {"error": "no PR found" + (f" for {exercise}" if exercise else "")}
        day = prs[-1]["day"]
        same_day = [p for p in prs if p["day"] == day]
        return {
            "day": day.isoformat(),
            "prs": [{k: v for k, v in p.items() if k != "day"} for p in same_day],
        }

    async def best(self, exercise: str) -> dict[str, Any]:
        name = self.resolve_exercise(exercise) or exercise
        b = all_time_best(self.sessions, name)
        return b or {"error": f"no {exercise} with a known load in the log"}

    async def last_time(self, exercise: str) -> dict[str, Any]:
        name = self.resolve_exercise(exercise) or exercise
        hits = [s for s in self.sessions if s.exercise(name)]
        if not hits:
            return {"error": f"never logged {exercise}"}
        s = hits[-1]
        ex = s.exercise(name)
        assert ex is not None
        return {
            "exercise": name,
            "day": s.day.isoformat(),
            "kind": s.kind,
            "sets": describe_sets(ex),
            "times_logged": len(hits),
        }

    async def progression(self, exercise: str, full: bool = False) -> dict[str, Any]:
        name = self.resolve_exercise(exercise) or exercise
        points = []
        for s in self.sessions:
            ex = comparable(s).exercise(name)
            if ex:
                top = best_set(ex)
                points.append(
                    {
                        "day": s.day.isoformat(),
                        "set": f"{top.weight_kg:g} kg x {top.reps}",
                        "e1rm": round(estimated_1rm(top.weight_kg, top.reps), 1),
                    }
                )
        if not points:
            return {"error": f"no {exercise} with a known load in the log"}
        best = max(points, key=lambda p: p["e1rm"])
        return {
            "exercise": name,
            "sessions": len(points),
            "first": points[0],
            "best": best,
            "last": points[-1],
            "recent": points[-5:],
            **({"points": points} if full else {}),
        }

    async def improvements(self, top: int = 5, include_machines: bool = False) -> dict[str, Any]:
        """Biggest gains in estimated 1RM, first session -> best, for well-logged lifts.

        Machine numbers aren't comparable across gyms, so by default only free weights count.
        """
        series: dict[str, list[tuple[date, float, str]]] = {}
        for s in self.sessions:
            for ex in comparable(s).exercises:
                if not include_machines and not FREE_WEIGHTS.search(ex.name):
                    continue
                b = best_set(ex)
                series.setdefault(ex.name, []).append(
                    (s.day, estimated_1rm(b.weight_kg, b.reps), f"{b.weight_kg:g} kg x {b.reps}")
                )
        rows = []
        for name, pts in series.items():
            if len(pts) < 4:
                continue
            first, best = pts[0], max(pts, key=lambda p: p[1])
            gain = best[1] - first[1]
            rows.append(
                {
                    "exercise": name,
                    "from": f"{first[2]} ({first[0]})",
                    "to": f"{best[2]} ({best[0]})",
                    "gain_kg": round(gain, 1),
                    "gain_pct": round(100 * gain / first[1]),
                    "sessions": len(pts),
                }
            )
        rows.sort(key=lambda r: -r["gain_pct"])
        return {"top": rows[: int(top)], "machines_included": include_machines}

    async def count_sessions(self, days: int = 30) -> dict[str, Any]:
        since = self.today - timedelta(days=int(days))
        pool = [s for s in self.sessions if s.day > since]
        kinds: dict[str, int] = {}
        for s in pool:
            kinds[s.kind] = kinds.get(s.kind, 0) + 1
        return {
            "days": int(days),
            "sessions": len(pool),
            "by_kind": kinds,
            "last": pool[-1].day.isoformat() if pool else None,
        }

    async def why(self, day: str | None = None) -> dict[str, Any]:
        regs = find_regressions(self.sessions)
        if day:
            d = date.fromisoformat(day)
        elif regs:
            d = max(regs)  # "why did my lifts drop?" -> the most recent drop
        else:
            return {"error": "no drop in performance found"}
        sessions = [s for s in self.sessions if s.day == d]
        if not sessions:
            return {"error": f"no session on {d.isoformat()}"}
        facts: list[dict[str, Any]] = []
        if self.memory_search:
            for s in sessions:
                facts += [
                    f
                    for f in await self.memory_search(session_key(s))
                    if f.get("relation") == "AFFECTED_BY"
                ]
        return {
            "day": d.isoformat(),
            "sessions": [session_key(s) for s in sessions],
            "drops": regs.get(d, []),
            "memory": facts,
        }

    def tools(self) -> list[Tool]:
        ex = {"exercise": "exercise name, e.g. bench, squat, lat pulldown"}
        return [
            Tool(
                "last_session",
                "most recent session, optionally of one kind",
                {"kind": "push|pull|upper|lower|full body|arms|deadlift"},
                self.last_session,
            ),
            Tool(
                "last_pr",
                "most recent personal record, optionally for one exercise",
                {"exercise": "optional exercise"},
                self.last_pr,
            ),
            Tool("best", "all-time best set and estimated 1RM for an exercise", ex, self.best),
            Tool("last_time", "when an exercise was last done and the sets", ex, self.last_time),
            Tool("progression", "estimated 1RM over time for an exercise", ex, self.progression),
            Tool(
                "count_sessions",
                "how many sessions in the last N days",
                {"days": "number of days"},
                self.count_sessions,
            ),
            Tool(
                "improvements",
                "lifts ranked by gain in estimated 1RM, first session to best",
                {"top": "how many, default 5", "include_machines": "true to rank machines too"},
                self.improvements,
            ),
            Tool(
                "why",
                "what memory says about a session where lifts dropped",
                {"day": "YYYY-MM-DD, empty = the most recent drop"},
                self.why,
            ),
        ]

    # ---------------- tier 0: recognise the common questions ----------------

    def parse_day(self, text: str) -> str | None:
        m = re.search(r"\d{4}-\d{2}-\d{2}", text)
        if m:
            return m[0]
        m = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\w*", text, re.IGNORECASE
        ) or re.search(r"\b(" + "|".join(MONTHS) + r")\w*\s+(\d{1,2})\b", text, re.IGNORECASE)
        if not m:
            return None
        a, b = m.groups()
        day, mon = (int(a), b) if a.isdigit() else (int(b), a)
        d = date(self.today.year, MONTHS.index(mon[:3].lower()) + 1, day)
        return (d if d <= self.today else d.replace(year=d.year - 1)).isoformat()

    def intent(self, q: str) -> tuple[str, dict[str, Any]] | None:
        ex = self.resolve_exercise(q)
        kind = next(
            (
                KIND_WORDS[k]
                for k in sorted(KIND_WORDS, key=len, reverse=True)
                if re.search(rf"\b{k}\b", q, re.IGNORECASE)
            ),
            None,
        )
        if WHY.search(q):
            return "why", {"day": self.parse_day(q)}
        if LAST_PR.search(q):
            return "last_pr", {"exercise": ex}
        if IMPROVED.search(q) and not ex:
            return "improvements", {"top": 5}
        if COUNT.search(q):
            m = re.search(r"(\d+)\s*days?", q)
            days = int(m[1]) if m else 7 if re.search(r"\bweek\b", q, re.IGNORECASE) else 30
            return "count_sessions", {"days": days}
        if ex and PROGRESS.search(q):
            return "progression", {"exercise": ex}
        if ex and LAST_TIME.search(q):
            return "last_time", {"exercise": ex}
        if ex and BEST.search(q):
            return "best", {"exercise": ex}
        if LAST_SESSION.search(q) and (
            kind or re.search(r"workout|session|training|gym|lift", q, re.IGNORECASE)
        ):
            return "last_session", {"kind": kind}
        return None

    def render(self, tool: str, r: dict[str, Any]) -> str:
        if "error" in r:
            return r["error"][0].upper() + r["error"][1:] + "."
        if tool == "last_session":
            return str(r["text"])
        if tool == "last_pr":
            d = date.fromisoformat(r["day"])
            parts = [
                f"{p['exercise']} {p['top_set']} (est. 1RM {p['e1rm']:g} kg"
                + (f", beating {p['previous_set']}" if p["previous_set"] else "")
                + ")"
                for p in r["prs"]
            ]
            return f"Your last PR was on {nice(d)}: " + "; ".join(parts) + "."
        if tool == "best":
            b, h = r["best_e1rm"], r["heaviest"]
            out = (
                f"Best {r['exercise']}: {b['set']} on {nice(b['day'])}, est. 1RM {b['e1rm']:g} kg."
            )
            if h and h["set"] != b["set"]:
                out += f" Heaviest single set: {h['set']} on {nice(h['day'])}."
            return out
        if tool == "last_time":
            return (
                f"You last did {r['exercise']} on {nice(date.fromisoformat(r['day']))} "
                f"({r['kind']}): {r['sets']}. Logged {r['times_logged']} times in total."
            )
        if tool == "progression":
            f, b, last = r["first"], r["best"], r["last"]
            return (
                f"{r['exercise'].title()} over {r['sessions']} sessions: est. 1RM "
                f"{f['e1rm']:g} kg ({f['day']}) -> best {b['e1rm']:g} kg ({b['set']}, "
                f"{b['day']}); latest {last['e1rm']:g} kg ({last['set']}, {last['day']})."
            )
        if tool == "improvements":
            rows = r["top"]
            if not rows:
                return "Not enough history to compare lifts yet."
            lines = [
                f"- {x['exercise']}: {x['from']} -> {x['to']}, +{x['gain_pct']}% est. 1RM"
                for x in rows
            ]
            note = (
                ""
                if r.get("machines_included")
                else "\n(Free weights only: machine numbers change from gym to gym.)"
            )
            head = "Biggest gains (estimated 1RM, first session to best):\n"
            return head + "\n".join(lines) + note
        if tool == "count_sessions":
            kinds = ", ".join(
                f"{n} {k}" for k, n in sorted(r["by_kind"].items(), key=lambda kv: -kv[1])
            )
            return f"{r['sessions']} sessions in the last {r['days']} days" + (
                f": {kinds}." if kinds else "."
            )
        if tool == "why":
            d = nice(date.fromisoformat(r["day"]))
            drops = ", ".join(f"{x['exercise']} {x['volume_change']:+.0%}" for x in r["drops"])
            out = f"On {d}" + (f" volume dropped: {drops}." if drops else ": no drop found.")
            causes = []
            for f in r["memory"]:
                obj = str(f.get("object", ""))
                props = f.get("props") or {}
                if isinstance(props, str):
                    import json

                    props = json.loads(props or "{}")
                if obj == "SleepDeficit":
                    causes.append(
                        f"short sleep (last night {props.get('last_night_h')} h, "
                        f"3-night average {props.get('avg_sleep_h')} h)"
                    )
                elif obj == "CalorieDeficit":
                    y = props.get("kcal_yesterday")
                    causes.append(
                        f"low calories ({round(y)} kcal the day before, " if y else "low calories ("
                    )
                    causes[-1] += f"{props.get('kcal_vs_target'):+} kcal/day over 3 days vs target)"
                elif obj.startswith("Injury:"):
                    causes.append(obj.split(":", 1)[1])
            out += (
                " Memory links it to " + " and ".join(causes) + "."
                if causes
                else " Memory has nothing that explains it."
            )
            return out
        return str(r)

    async def answer(self, question: str, llm: Asker | None = None) -> Answer:
        hit = self.intent(question)
        tools = {t.name: t for t in self.tools()}
        if hit:
            name, args = hit
            result = await tools[name].fn(**{k: v for k, v in args.items() if v is not None})
            return Answer(self.render(name, result), Tier.code, name)
        if llm is None:
            return Answer(HELP, Tier.code)
        try:
            run = await run_agent(question, self.tools(), llm, self.today.isoformat())
        except Exception:  # noqa: BLE001 - model or proxy down: fall back to help text
            return Answer("I couldn't work that one out right now. " + HELP, Tier.code)
        return Answer(run.answer, Tier.large, "agent", run.steps)


HELP = (
    "Try: 'what's my last PR?', 'what did I do last push?', 'best bench', "
    "'how is my squat progressing?', 'when did I last deadlift?', "
    "'why did my lifts drop?'."
)
