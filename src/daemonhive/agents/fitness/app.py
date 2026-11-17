"""Fitness agent service: A2A server + the handler Concierge forwards workout logs to."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import FastAPI

from daemonhive.agents.fitness.agent import FitnessAgent
from daemonhive.agents.fitness.parser import Session
from daemonhive.common.a2a import A2AClient, A2AServer, AgentCard, Skill, TaskRequest
from daemonhive.common.llm import AgentLLM
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
    ],
)


class Store:
    async def log_session(self, s: Session) -> int:
        return await fitness_db.save(s)

    async def last_session(self, kind: str, before: date) -> Session | None:
        return await fitness_db.load_last(kind, before)


class MemoryClient:
    """Calls memory-mcp over streamable HTTP as the 'fitness' identity."""

    def __init__(self, url: str) -> None:
        self.url = url

    async def add_fact(
        self,
        source: str,
        subject: str,
        relation: str,
        obj: str,
        valid_from: str,
        props: dict[str, Any],
    ) -> None:
        from fastmcp import Client

        async with Client(self.url) as c:
            await c.call_tool(
                "add_fact",
                {
                    "agent": source,
                    "subject": subject,
                    "relation": relation,
                    "obj": obj,
                    "valid_from": valid_from,
                    "props": props,
                },
            )


agent = FitnessAgent(
    store=Store(),
    memory=MemoryClient(os.environ.get("MEMORY_MCP_URL", "http://memory-mcp:8200/mcp")),
    peer=A2AClient("fitness", os.environ.get("A2A_TOKEN_FITNESS", "dev-fitness")),
    writer=AgentLLM("fitness"),
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


server.mount(app)
