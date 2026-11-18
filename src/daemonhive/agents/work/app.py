"""Work agent exposed over A2A. Plans today's deep-work block around last night's sleep."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import FastAPI

from daemonhive.agents.work.planner import plan_deep_work
from daemonhive.common.a2a import A2AClient, A2AServer, AgentCard, Skill, TaskRequest, TaskState

WELLBEING_URL = os.environ.get("WELLBEING_URL", "http://wellbeing:8102")

CARD = AgentCard(
    name="work",
    description="Owns tasks and the calendar. Plans deep work around how you slept.",
    url=os.environ.get("WORK_URL", "http://work:8103"),
    skills=[
        Skill(
            id="chat",
            name="Plan my day",
            description="Place today's 2-hour deep-work block.",
            examples=["plan my day", "when should I do deep work today?"],
        )
    ],
)

app = FastAPI(title="work")
server = A2AServer(
    CARD, tokens={os.environ.get("A2A_TOKEN_CONCIERGE", "dev-concierge"): "concierge"}
)
a2a = A2AClient("work", os.environ.get("A2A_TOKEN_WORK", "dev-work"))


async def plan_message(today: date) -> str:
    res = await a2a.send(WELLBEING_URL, "recovery_summary", {"until": today.isoformat(), "days": 1})
    known = res.state is TaskState.completed and res.output.get("nights_logged")
    short_night = bool(known) and "SleepDeficit" in res.output.get("flags", [])
    # TODO(#2): pull busy slots from Google Calendar via work-mcp
    block = plan_deep_work(today, [], short_night=short_night)
    if block is None:
        return "No 2-hour slot today. Protect tomorrow morning instead."
    when = f"{block.start:%H:%M}-{block.end:%H:%M}"
    if short_night:
        return f"Deep work {when}. Pushed back: you slept {res.output['avg_sleep_h']} h last night."
    if not known:
        return f"Deep work {when}. (No sleep logged for last night, assuming it was fine.)"
    return f"Deep work {when}. You slept {res.output['avg_sleep_h']} h, so mornings are fair game."


@server.skill("chat", allowed_callers={"concierge"})
async def chat(req: TaskRequest) -> dict[str, Any]:
    return {"message": await plan_message(date.today())}


server.mount(app)
