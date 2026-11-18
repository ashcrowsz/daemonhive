"""Well-being agent exposed over A2A.

Skills:
  chat              - log sleep / meals from a Telegram line (tier 0 grammar)
  recovery_summary  - aggregates + flags for other agents, never raw rows
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import FastAPI

from daemonhive.agents.wellbeing.logs import LogError, parse_log
from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow, recovery_summary
from daemonhive.common.a2a import A2AServer, AgentCard, Skill, TaskRequest

CARD = AgentCard(
    name="wellbeing",
    description="Owns nutrition, sleep and body weight. Shares summaries, never raw logs.",
    url=os.environ.get("WELLBEING_URL", "http://wellbeing:8102"),
    skills=[
        Skill(
            id="chat",
            name="Log sleep or a meal",
            description="Parse and store one sleep or meal entry.",
            examples=["slept 5.5h", "2026-11-02 dinner pasta 900 kcal"],
        ),
        Skill(
            id="recovery_summary",
            name="Recovery summary",
            description="Average sleep, calorie balance and recovery flags over the last N days.",
            input_schema={
                "type": "object",
                "properties": {
                    "until": {"type": "string", "format": "date"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 14},
                },
                "required": ["until"],
            },
            examples=["How did I recover over the 3 days before 2026-11-03?"],
        ),
    ],
)

app = FastAPI(title="wellbeing")
server = A2AServer(
    CARD,
    tokens={
        os.environ.get("A2A_TOKEN_CONCIERGE", "dev-concierge"): "concierge",
        os.environ.get("A2A_TOKEN_FITNESS", "dev-fitness"): "fitness",
        os.environ.get("A2A_TOKEN_WORK", "dev-work"): "work",
    },
)


class PostgresRepo:
    """Only this agent's role can read the wellbeing schema."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Any = None

    async def pool(self) -> Any:
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=3)
        return self._pool

    async def add_sleep(self, row: SleepRow) -> None:
        p = await self.pool()
        await p.execute(
            "INSERT INTO wellbeing.sleep (night_of, hours) VALUES ($1, $2) "
            "ON CONFLICT (night_of) DO UPDATE SET hours = EXCLUDED.hours",
            row.night_of,
            row.hours,
        )

    async def add_meal(self, row: MealRow, label: str) -> None:
        p = await self.pool()
        await p.execute(
            "INSERT INTO wellbeing.meal (day, label, kcal) VALUES ($1, $2, $3)",
            row.day,
            label,
            row.kcal,
        )

    async def sleep(self) -> list[SleepRow]:
        p = await self.pool()
        rows = await p.fetch("SELECT night_of, hours FROM wellbeing.sleep")
        return [SleepRow(r["night_of"], float(r["hours"])) for r in rows]

    async def meals(self) -> list[MealRow]:
        p = await self.pool()
        rows = await p.fetch("SELECT day, kcal FROM wellbeing.meal")
        return [MealRow(r["day"], r["kcal"]) for r in rows]


repo = PostgresRepo(os.environ.get("DATABASE_URL", "postgresql://hive:hive@localhost:5432/hive"))
KCAL_TARGET = int(os.environ.get("KCAL_TARGET", "2800"))


@server.skill("chat", allowed_callers={"concierge"})
async def chat(req: TaskRequest) -> dict[str, Any]:
    try:
        parsed = parse_log(req.input["text"], today=date.today())
    except LogError as e:
        return {"message": f"Didn't catch that: {e}"}
    if parsed.sleep:
        await repo.add_sleep(parsed.sleep)
        return {
            "message": f"Logged {parsed.sleep.hours:g} h of sleep (night of {parsed.sleep.night_of})."
        }
    assert parsed.meal
    await repo.add_meal(parsed.meal, parsed.label)
    return {"message": f"Logged {parsed.label}: {parsed.meal.kcal} kcal on {parsed.meal.day}."}


@server.skill("recovery_summary", allowed_callers={"fitness", "work"})
async def recovery(req: TaskRequest) -> dict[str, Any]:
    until = date.fromisoformat(req.input["until"])
    days = int(req.input.get("days", 3))
    return recovery_summary(
        await repo.sleep(), await repo.meals(), until=until, days=days, kcal_target=KCAL_TARGET
    )


server.mount(app)
