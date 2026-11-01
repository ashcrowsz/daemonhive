"""Well-being agent exposed over A2A."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import FastAPI

from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow, recovery_summary
from daemonhive.common.a2a import A2AServer, AgentCard, Skill, TaskRequest

CARD = AgentCard(
    name="wellbeing",
    description="Owns nutrition, sleep and body weight. Shares summaries, never raw logs.",
    url=os.environ.get("WELLBEING_URL", "http://wellbeing:8102"),
    skills=[
        Skill(
            id="recovery_summary",
            name="Recovery summary",
            description="Average sleep, calorie balance and recovery flags over the last N days.",
            input_schema={
                "type": "object",
                "properties": {"until": {"type": "string", "format": "date"},
                               "days": {"type": "integer", "minimum": 1, "maximum": 14}},
                "required": ["until"],
            },
            examples=["How did I recover over the 3 days before 2026-11-03?"],
        )
    ],
)

app = FastAPI(title="wellbeing")
server = A2AServer(
    CARD,
    tokens={os.environ.get("A2A_TOKEN_FITNESS", "dev-fitness"): "fitness",
            os.environ.get("A2A_TOKEN_WORK", "dev-work"): "work"},
)


class Repo:
    """Postgres access via wellbeing-db MCP in prod; replaced in tests."""

    async def sleep(self) -> list[SleepRow]:
        return []

    async def meals(self) -> list[MealRow]:
        return []


repo = Repo()
KCAL_TARGET = int(os.environ.get("KCAL_TARGET", "2800"))


@server.skill("recovery_summary", allowed_callers={"fitness", "work"})
async def recovery(req: TaskRequest) -> dict[str, Any]:
    until = date.fromisoformat(req.input["until"])
    days = int(req.input.get("days", 3))
    return recovery_summary(await repo.sleep(), await repo.meals(),
                            until=until, days=days, kcal_target=KCAL_TARGET)


server.mount(app)
