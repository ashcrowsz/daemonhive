"""Fitness agent service: A2A server + the handler Concierge forwards workout logs to."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import FastAPI

from daemonhive.agents.fitness.agent import FitnessAgent
from daemonhive.agents.fitness.parser import Session
from daemonhive.agents.fitness.qa import FitnessQA, describe_sets
from daemonhive.agents.fitness.records import find_prs, find_regressions, session_key
from daemonhive.common.a2a import A2AClient, A2AServer, AgentCard, Skill, TaskRequest
from daemonhive.common.llm import AgentLLM
from daemonhive.common.memory_client import MemoryClient
from daemonhive.mcp import fitness_db

CARD = AgentCard(
    name="fitness",
    description="Owns workout logs and progression. Detects PRs and regressions.",
    url=os.environ.get("FITNESS_URL", "http://fitness:8101"),
    skills=[
        Skill(
            id="log_workout",
            name="Log a workout",
            description="Parse a workout log, store it, compare with the last session.",
            examples=["Push 2026-11-03\nBench Press 120kg 3x3 RPE 7"],
        ),
        Skill(
            id="progression",
            name="Progression",
            description="Top set and volume over time for one exercise.",
        ),
        Skill(
            id="ask",
            name="Answer a training question",
            description="Last PR, last session of a kind, bests, progression, why a lift dropped.",
            examples=["what's my last PR?", "what did I do last push?"],
        ),
        Skill(
            id="dashboard",
            name="Dashboard data",
            description="Read-only views of the training history for the web UI.",
        ),
    ],
)


class Store:
    async def log_session(self, s: Session) -> int:
        return await fitness_db.save(s)

    async def last_session(self, kind: str, before: date) -> Session | None:
        return await fitness_db.load_last(kind, before)


memory = MemoryClient("fitness")
llm = AgentLLM("fitness")
agent = FitnessAgent(
    store=Store(),
    memory=memory,
    peer=A2AClient("fitness", os.environ.get("A2A_TOKEN_FITNESS", "dev-fitness")),
    writer=llm,
    wellbeing_url=os.environ.get("WELLBEING_URL", "http://wellbeing:8102"),
)

app = FastAPI(title="fitness")
server = A2AServer(
    CARD, tokens={os.environ.get("A2A_TOKEN_CONCIERGE", "dev-concierge"): "concierge"}
)


@server.skill("log_workout", allowed_callers={"concierge"})
async def log_workout(req: TaskRequest) -> dict[str, Any]:
    out = await agent.handle_log(req.input["text"])
    return {"message": out.message, "trace": out.trace}


@server.skill("progression", allowed_callers={"concierge", "work"})
async def progression(req: TaskRequest) -> dict[str, Any]:
    rows = await fitness_db.get_progression(req.input["exercise"], int(req.input.get("weeks", 12)))
    return {"rows": [{k: str(v) for k, v in r.items()} for r in rows]}


async def qa() -> FitnessQA:
    async def facts(key: str) -> list[dict[str, Any]]:
        return await memory.search(key, key)

    return FitnessQA(await fitness_db.load_all(), date.today(), facts)


@server.skill("ask", allowed_callers={"concierge"})
async def ask(req: TaskRequest) -> dict[str, Any]:
    a = await (await qa()).answer(req.input["text"], llm)
    return {"message": a.text, "tier": int(a.tier), "tool": a.tool, "steps": a.steps}


@server.skill("dashboard", allowed_callers={"concierge"})
async def dashboard(req: TaskRequest) -> dict[str, Any]:
    q = await qa()
    view = req.input.get("view", "overview")
    sessions = q.sessions
    if not sessions:
        return {"empty": True}
    prs = find_prs(sessions)
    regs = find_regressions(sessions)
    pr_days = {p["day"] for p in prs}
    if view == "sessions":
        return {
            "sessions": [
                {
                    "day": s.day.isoformat(),
                    "kind": s.kind,
                    "exercises": len(s.exercises),
                    "sets": sum(len(e.sets) for e in s.exercises),
                    "estimated": "date estimated" in s.notes,
                    "regression": s.day in regs,
                    "prs": sum(1 for p in prs if p["day"] == s.day),
                }
                for s in reversed(sessions)
            ]
        }
    if view == "session":
        s = next(
            (
                x
                for x in sessions
                if x.day.isoformat() == req.input.get("day")
                and (not req.input.get("kind") or x.kind == req.input["kind"])
            ),
            None,
        )
        if s is None:
            return {"error": "no such session"}
        return {
            "day": s.day.isoformat(),
            "kind": s.kind,
            "key": session_key(s),
            "notes": s.notes,
            "drops": regs.get(s.day, []),
            "prs": [{**p, "day": p["day"].isoformat()} for p in prs if p["day"] == s.day],
            "exercises": [
                {
                    "name": e.name,
                    "summary": describe_sets(e),
                    "sets": [
                        {"kg": x.weight_kg, "reps": x.reps, "rpe": x.rpe, "load": x.load}
                        for x in e.sets
                    ],
                }
                for e in s.exercises
            ],
        }
    if view == "prs":
        return {"prs": [{**p, "day": p["day"].isoformat()} for p in reversed(prs)]}
    if view == "progression":
        return await q.progression(req.input.get("exercise", "bench press"), full=True)
    counts: dict[str, int] = {}
    for s in sessions:
        for e in s.exercises:
            counts[e.name] = counts.get(e.name, 0) + 1
    lifts = {}
    for name in ("bench press", "back squat", "deadlift", "incline bench press", "lat pulldown"):
        b = await q.best(name)
        if "error" not in b:
            lifts[name] = {**b["best_e1rm"], "day": b["best_e1rm"]["day"].isoformat()}
    weeks: dict[str, int] = {}
    for s in sessions:
        wk = s.day.isocalendar()
        key = f"{wk.year}-W{wk.week:02d}"
        weeks[key] = weeks.get(key, 0) + 1
    last_pr = await q.last_pr()
    return {
        "sessions": len(sessions),
        "first": sessions[0].day.isoformat(),
        "last": sessions[-1].day.isoformat(),
        "kinds": {
            k: sum(1 for s in sessions if s.kind == k) for k in sorted({s.kind for s in sessions})
        },
        "sets": sum(len(e.sets) for s in sessions for e in s.exercises),
        "prs": len(prs),
        "regressions": len(regs),
        "pr_days": len(pr_days),
        "last_pr": last_pr,
        "best_lifts": lifts,
        "weekly": weeks,
        "exercises": sorted((n for n, c in counts.items() if c >= 3), key=lambda n: -counts[n]),
        "last_session": (await q.last_session())["text"],
    }


server.mount(app)
