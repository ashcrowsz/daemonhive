"""Answer questions about sleep, food, body weight and diet phase.

Well-being owns this data, so it answers from its own rows; the diet phase comes from the
memory graph (IN_PHASE facts), which Well-being is allowed to read.
Tier 0 for the common questions, the shared tool loop for the rest.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

from daemonhive.agents.fitness.qa import Answer, nice
from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow
from daemonhive.common.agentic import Asker, Tool, run_agent
from daemonhive.common.tiers import Tier

Timeline = Callable[[], Awaitable[list[dict[str, Any]]]]

SLEEP = re.compile(r"\bsle(e|p)p?\w*|\bslept\b|\bnights?\b|\bbed\b", re.IGNORECASE)
FOOD = re.compile(
    r"\bcalorie\w*|\bkcal\b|\beat\w*|\bate\b|\bfood\b|\bnutrition\b|\bmeals?\b", re.IGNORECASE
)
WEIGHT = re.compile(r"\bweigh\w*|\bbody ?weight\b|\bkg\b", re.IGNORECASE)
PHASE = re.compile(r"\bcut\w*|\bbulk\w*|\bmaintenance\b|\bphase\b|\bdiet\b", re.IGNORECASE)


def window(q: str) -> int:
    if re.search(r"last night|yesterday", q, re.IGNORECASE):
        return 1
    m = re.search(r"(\d+)\s*(day|week|month)s?", q, re.IGNORECASE)
    if m:
        return int(m[1]) * {"day": 1, "week": 7, "month": 30}[m[2].lower()]
    if re.search(r"\bmonth\b", q, re.IGNORECASE):
        return 30
    return 7


class WellbeingQA:
    def __init__(
        self,
        sleep: list[SleepRow],
        meals: list[MealRow],
        weights: list[tuple[date, float]],
        today: date,
        kcal_target: int,
        timeline: Timeline | None = None,
    ) -> None:
        self.sleep = sorted(sleep, key=lambda s: s.night_of)
        self.meals = meals
        self.weights = sorted(weights)
        self.today = today
        self.kcal_target = kcal_target
        self.timeline = timeline

    def _days(self, days: int) -> tuple[date, date]:
        last = max((s.night_of for s in self.sleep), default=self.today - timedelta(days=1))
        end = min(self.today - timedelta(days=1), last)
        return end - timedelta(days=int(days) - 1), end

    async def sleep_stats(self, days: int = 7) -> dict[str, Any]:
        start, end = self._days(days)
        rows = [s for s in self.sleep if start <= s.night_of <= end]
        if not rows:
            return {"error": "no sleep logged in that window"}
        hours = [s.hours for s in rows]
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "nights": len(rows),
            "avg_h": round(sum(hours) / len(hours), 1),
            "min_h": min(hours),
            "short_nights": sum(h < 6 for h in hours),
            "worst_night": min(rows, key=lambda s: s.hours).night_of.isoformat(),
        }

    async def kcal_stats(self, days: int = 7) -> dict[str, Any]:
        start, end = self._days(days)
        per_day: dict[date, int] = {}
        for m in self.meals:
            if start <= m.day <= end:
                per_day[m.day] = per_day.get(m.day, 0) + m.kcal
        if not per_day:
            return {"error": "no meals logged in that window"}
        avg = round(sum(per_day.values()) / len(per_day))
        low = min(per_day, key=lambda d: per_day[d])
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": len(per_day),
            "avg_kcal": avg,
            "target": self.kcal_target,
            "vs_target": avg - self.kcal_target,
            "lowest_day": low.isoformat(),
            "lowest_kcal": per_day[low],
        }

    async def body_weight(self) -> dict[str, Any]:
        if not self.weights:
            return {"error": "no body weight logged"}
        (d0, w0), (d1, w1) = self.weights[0], self.weights[-1]
        return {
            "latest_kg": w1,
            "on": d1.isoformat(),
            "first_kg": w0,
            "first_on": d0.isoformat(),
            "change_kg": round(w1 - w0, 1),
            "entries": len(self.weights),
        }

    async def phase(self) -> dict[str, Any]:
        facts = [
            f
            for f in (await self.timeline() if self.timeline else [])
            if f.get("relation") == "IN_PHASE"
        ]
        if not facts:
            return {"error": "no diet phase in memory"}
        history = [
            {
                "phase": str(f["object"]).split(":", 1)[-1],
                "from": f["valid_from"],
                "to": f.get("valid_to"),
            }
            for f in facts
        ]
        return {"current": history[-1]["phase"], "since": history[-1]["from"], "history": history}

    def tools(self) -> list[Tool]:
        d = {"days": "window in days, default 7"}
        return [
            Tool(
                "sleep_stats",
                "average and shortest sleep over the last N days",
                d,
                self.sleep_stats,
            ),
            Tool(
                "kcal_stats",
                "average daily calories vs target over the last N days",
                d,
                self.kcal_stats,
            ),
            Tool("body_weight", "latest body weight and change", {}, self.body_weight),
            Tool("phase", "current diet phase (cut / maintenance) and its history", {}, self.phase),
        ]

    def intent(self, q: str) -> tuple[str, dict[str, Any]] | None:
        if PHASE.search(q):
            return "phase", {}
        if SLEEP.search(q):
            return "sleep_stats", {"days": window(q)}
        if FOOD.search(q):
            return "kcal_stats", {"days": window(q)}
        if WEIGHT.search(q):
            return "body_weight", {}
        return None

    def render(self, tool: str, r: dict[str, Any]) -> str:
        if "error" in r:
            return r["error"][0].upper() + r["error"][1:] + "."
        if tool == "sleep_stats":
            if r["nights"] == 1:
                return f"You slept {r['avg_h']:g} h on the night of {r['to']}."
            return (
                f"Over the last {r['nights']} nights you slept {r['avg_h']:g} h on average, "
                f"shortest {r['min_h']:g} h ({r['worst_night']}); "
                f"{r['short_nights']} night(s) under 6 h."
            )
        if tool == "kcal_stats":
            return (
                f"Over the last {r['days']} days you ate {r['avg_kcal']} kcal/day on average "
                f"({r['vs_target']:+d} vs your {r['target']} target); lowest day "
                f"{r['lowest_kcal']} kcal on {r['lowest_day']}."
            )
        if tool == "body_weight":
            return (
                f"Last logged body weight: {r['latest_kg']:g} kg on "
                f"{nice(date.fromisoformat(r['on']))} ({r['change_kg']:+g} kg since "
                f"{r['first_on']})."
            )
        if tool == "phase":
            past = ", ".join(f"{h['phase']} from {h['from']}" for h in r["history"])
            return f"You're in a {r['current']} since {r['since']}. History: {past}."
        return str(r)

    async def answer(self, question: str, llm: Asker | None = None) -> Answer:
        hit = self.intent(question)
        tools = {t.name: t for t in self.tools()}
        if hit:
            name, args = hit
            return Answer(self.render(name, await tools[name].fn(**args)), Tier.code, name)
        if llm is None:
            return Answer(HELP, Tier.code)
        try:
            run = await run_agent(question, self.tools(), llm, self.today.isoformat())
        except Exception:  # noqa: BLE001 - model or proxy down: fall back to help text
            return Answer("I couldn't work that one out right now. " + HELP, Tier.code)
        return Answer(run.answer, Tier.large, "agent", run.steps)


HELP = (
    "Try: 'how did I sleep this week?', 'average calories last 30 days', "
    "'what's my weight?', 'am I cutting?'."
)
