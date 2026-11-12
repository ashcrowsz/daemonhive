"""Concierge: receives every Telegram message from the gateway and dispatches it."""

from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel

from daemonhive.agents.concierge.routing import (
    ROUTER_PROMPT,
    Route,
    parse_router_answer,
    route_by_rules,
)
from daemonhive.common.a2a import A2AClient, TaskState
from daemonhive.common.llm import AgentLLM
from daemonhive.common.tiers import Tier, TierLedger

PEERS = {
    "fitness": (os.environ.get("FITNESS_URL", "http://fitness:8101"), "log_workout"),
    "wellbeing": (os.environ.get("WELLBEING_URL", "http://wellbeing:8102"), "chat"),
    "work": (os.environ.get("WORK_URL", "http://work:8103"), "chat"),
}

app = FastAPI(title="concierge")
a2a = A2AClient("concierge", os.environ.get("A2A_TOKEN_CONCIERGE", "dev-concierge"))
llm = AgentLLM("concierge")
ledger = TierLedger()


class Inbound(BaseModel):
    chat_id: int
    text: str


async def route(text: str) -> Route:
    r = route_by_rules(text)
    if r:
        return r
    names = parse_router_answer(await llm.ask(ROUTER_PROMPT, text, tier=Tier.small, max_tokens=20))
    if names:
        return Route(names, Tier.small, "small model")
    return Route(("work",), Tier.small, "fallback")


@app.post("/inbound")
async def inbound(msg: Inbound) -> dict[str, object]:
    r = await route(msg.text)
    ledger.record(r.tier)
    replies: list[str] = []
    for name in r.agents:
        url, skill = PEERS[name]
        res = await a2a.send(url, skill, {"text": msg.text})
        if res.state is TaskState.completed:
            replies.append(str(res.output.get("message", "")))
        else:
            replies.append(f"({name} is unavailable right now, I kept your message.)")
    return {"reply": "\n\n".join(x for x in replies if x), "route": r.reason}


@app.get("/stats")
async def stats() -> dict[str, float]:
    return {f"tier{int(t)}_share": ledger.share(t) for t in Tier}
