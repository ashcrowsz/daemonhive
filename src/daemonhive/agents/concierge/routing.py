"""Concierge routing: rules first, small model second, big model only when stuck."""

from __future__ import annotations

import re
from dataclasses import dataclass

from daemonhive.agents.fitness.parser import HEADER, LINE
from daemonhive.common.tiers import Tier

AGENTS = ("fitness", "wellbeing", "work")

KEYWORDS: dict[str, tuple[str, ...]] = {
    "fitness": ("workout", "bench", "squat", "deadlift", "gym", "pr", "sets", "reps", "rpe"),
    "wellbeing": (
        "slept",
        "sleep",
        "ate",
        "kcal",
        "calories",
        "protein",
        "weight",
        "breakfast",
        "lunch",
        "dinner",
        "meal",
        "nap",
    ),
    "work": ("meeting", "task", "deadline", "calendar", "schedule", "todo", "project", "focus"),
}

SLEEP_LOG = re.compile(r"^\s*(slept|sleep)\s+\d+(\.\d+)?\s*h", re.IGNORECASE)
MEAL_LOG = re.compile(r"^\s*(breakfast|lunch|dinner|snack)\b.*\d+\s*kcal", re.IGNORECASE)


@dataclass(frozen=True)
class Route:
    agents: tuple[str, ...]
    tier: Tier
    reason: str


def looks_like_workout_log(text: str) -> bool:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2 or not HEADER.match(lines[0]):
        return False
    body = [ln for ln in lines[1:] if not ln.startswith("#")]
    return bool(body) and sum(bool(LINE.match(ln)) for ln in body) / len(body) >= 0.5


def route_by_rules(text: str) -> Route | None:
    if looks_like_workout_log(text):
        return Route(("fitness",), Tier.code, "workout grammar")
    if SLEEP_LOG.match(text) or MEAL_LOG.match(text):
        return Route(("wellbeing",), Tier.code, "wellbeing log pattern")
    words = set(re.findall(r"[a-z]+", text.lower()))
    hits = tuple(a for a in AGENTS if words & set(KEYWORDS[a]))
    if len(hits) == 1:
        return Route(hits, Tier.code, f"keywords -> {hits[0]}")
    return None  # zero or several domains: let a model decide


ROUTER_PROMPT = """Classify the user message into the agents that should handle it.
Agents: fitness (training), wellbeing (sleep, food, body weight), work (tasks, calendar).
Answer with a comma-separated list of agent names, or 'none'."""


def parse_router_answer(answer: str) -> tuple[str, ...]:
    names = tuple(a for a in AGENTS if a in answer.lower())
    return names
