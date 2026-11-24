"""Concierge routing: rules first, small model second, big model only when stuck."""

from __future__ import annotations

import re
from dataclasses import dataclass

from daemonhive.agents.fitness.parser import HEADER, LINE
from daemonhive.agents.wellbeing.logs import is_wellbeing_log
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
    "work": (
        "meeting",
        "task",
        "deadline",
        "calendar",
        "schedule",
        "todo",
        "project",
        "focus",
        "plan",
        "brief",
    ),
}


@dataclass(frozen=True)
class Route:
    agents: tuple[str, ...]
    tier: Tier
    reason: str
    skill: str = ""  # empty: the agent's default skill for incoming messages


QUESTION = re.compile(
    r"\?\s*$|^\s*(what|what's|whats|when|how|which|who|why|did|do|does|is|am|are|was|were|"
    r"show|tell|list|give|have i|where|can you)\b",
    re.IGNORECASE,
)
WELLBEING_TOPICS = re.compile(
    r"\b(sleep\w*|slept|nights?|calorie\w*|kcal|eat\w*|ate|food|meals?|weigh\w*|"
    r"body ?weight|cut\w*|bulk\w*|maintenance|phase|diet|nutrition)\b",
    re.IGNORECASE,
)
WORK_TOPICS = re.compile(
    r"\b(plan|brief|schedule|focus|task|meeting|calendar|deep work)\b", re.IGNORECASE
)
TRAINING_TOPICS = re.compile(
    r"\b(prs?|lifts?|lifting|bench|squat\w*|deadlift\w*|workouts?|sessions?|train\w*|gym|"
    r"best|heaviest|max|1rm|progress\w*|exercises?|push|pull|upper|lower|legs?|curl\w*|"
    r"press|rows?|pulldown|sets?|reps?|volume|strength|stronger|weaker)\b",
    re.IGNORECASE,
)
ASK_SKILL = {"fitness": "ask", "wellbeing": "ask"}  # work answers questions on "chat"


def is_question(text: str) -> bool:
    return bool(QUESTION.search(text))


def route_question(text: str) -> Route | None:
    """Questions with a clear topic go to the owning agent's `ask` skill. Tier 0.

    No clear topic ("how am I doing lately?"): None, and the small model decides.
    """
    if not is_question(text):
        return None
    if WORK_TOPICS.search(text):
        return Route(("work",), Tier.code, "question -> work")
    training = TRAINING_TOPICS.search(text)
    if WELLBEING_TOPICS.search(text) and not training:
        return Route(("wellbeing",), Tier.code, "question -> wellbeing", "ask")
    if training:
        return Route(("fitness",), Tier.code, "question -> fitness", "ask")
    return None


def looks_like_workout_log(text: str) -> bool:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2 or not HEADER.match(lines[0]):
        return False
    body = [ln for ln in lines[1:] if not ln.startswith("#")]
    return bool(body) and sum(bool(LINE.match(ln)) for ln in body) / len(body) >= 0.5


def route_by_rules(text: str) -> Route | None:
    if looks_like_workout_log(text):
        return Route(("fitness",), Tier.code, "workout grammar")
    if is_wellbeing_log(text):
        return Route(("wellbeing",), Tier.code, "wellbeing log pattern")
    q = route_question(text)
    if q:
        return q
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
