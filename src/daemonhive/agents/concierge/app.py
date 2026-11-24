"""Concierge: receives every message (Telegram or the web UI) and dispatches it.

It also serves the web UI's read-only API. Concierge owns no data: every number comes from
the owning agent over A2A, and the graph comes from memory-mcp as the read-only 'viewer'.
"""

from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from daemonhive.agents.concierge.routing import (
    ASK_SKILL,
    ROUTER_PROMPT,
    Route,
    is_question,
    parse_router_answer,
    route_by_rules,
)
from daemonhive.common.a2a import A2AClient, TaskState
from daemonhive.common.llm import AgentLLM
from daemonhive.common.memory_client import MemoryClient
from daemonhive.common.tiers import Tier, TierLedger
from daemonhive.mcp.permissions import POLICY

PEERS = {
    "fitness": (os.environ.get("FITNESS_URL", "http://fitness:8101"), "log_workout"),
    "wellbeing": (os.environ.get("WELLBEING_URL", "http://wellbeing:8102"), "chat"),
    "work": (os.environ.get("WORK_URL", "http://work:8103"), "chat"),
}

app = FastAPI(title="concierge")
# answers can involve a couple of local model calls: give peers time
a2a = A2AClient("concierge", os.environ.get("A2A_TOKEN_CONCIERGE", "dev-concierge"), timeout=150)
llm = AgentLLM("concierge")
ledger = TierLedger()
viewer = MemoryClient("viewer")
AUDIT = Path(os.environ.get("AUDIT_LOG", "audit/memory.jsonl"))


class Inbound(BaseModel):
    chat_id: int = 0
    text: str


async def route(text: str) -> Route:
    r = route_by_rules(text)
    if r:
        return r
    names = parse_router_answer(await llm.ask(ROUTER_PROMPT, text, tier=Tier.small, max_tokens=20))
    # a question the rules couldn't place still goes to the `ask` skill of whoever owns it
    skill = "ask" if is_question(text) else ""
    if names:
        return Route(names, Tier.small, "small model", skill)
    return Route(("work",), Tier.small, "fallback")


@app.post("/inbound")
async def inbound(msg: Inbound) -> dict[str, object]:
    r = await route(msg.text)
    ledger.record(r.tier)
    replies: list[str] = []
    answer_tier = int(r.tier)
    steps: list[Any] = []
    for name in r.agents:
        url, default_skill = PEERS[name]
        # "ask" = each agent's question skill where it has one (Work answers on "chat")
        skill = ASK_SKILL.get(name, default_skill) if r.skill == "ask" else default_skill
        res = await a2a.send(url, skill, {"text": msg.text})
        if res.state is TaskState.completed:
            replies.append(str(res.output.get("message", "")))
            answer_tier = max(answer_tier, int(res.output.get("tier", 0)))
            steps += res.output.get("steps", []) or []
        else:
            replies.append(f"({name} is unavailable right now, I kept your message.)")
    return {
        "reply": "\n\n".join(x for x in replies if x),
        "route": r.reason,
        "agents": list(r.agents),
        "tier": answer_tier,
        "steps": steps,
    }


@app.get("/stats")
async def stats() -> dict[str, float]:
    return {f"tier{int(t)}_share": ledger.share(t) for t in Tier}


# ---------------- read-only API for the web UI ----------------


async def peer(name: str, skill: str, payload: dict[str, Any]) -> dict[str, Any]:
    res = await a2a.send(PEERS[name][0], skill, payload)
    if res.state is not TaskState.completed:
        return {"error": f"{name} unavailable: {res.error}"}
    return dict(res.output)


@app.post("/api/chat")
async def chat(msg: Inbound) -> dict[str, object]:
    return await inbound(msg)


@app.get("/api/overview")
async def overview() -> dict[str, Any]:
    return {
        "fitness": await peer("fitness", "dashboard", {"view": "overview"}),
        "wellbeing": await peer("wellbeing", "dashboard", {"days": 120}),
    }


@app.get("/api/sessions")
async def sessions() -> dict[str, Any]:
    return await peer("fitness", "dashboard", {"view": "sessions"})


@app.get("/api/session")
async def session(day: str, kind: str = "") -> dict[str, Any]:
    return await peer("fitness", "dashboard", {"view": "session", "day": day, "kind": kind})


@app.get("/api/prs")
async def prs() -> dict[str, Any]:
    return await peer("fitness", "dashboard", {"view": "prs"})


@app.get("/api/progression")
async def progression(exercise: str = "bench press") -> dict[str, Any]:
    return await peer("fitness", "dashboard", {"view": "progression", "exercise": exercise})


@app.get("/api/recovery")
async def recovery(days: int = 120) -> dict[str, Any]:
    return await peer("wellbeing", "dashboard", {"days": days})


@app.get("/api/graph")
async def graph(limit: int = 2000) -> dict[str, Any]:
    policy = {
        name: {
            "read": sorted(s.read),
            "write": sorted(s.write_entities),
            "relations": sorted(s.write_relations),
        }
        for name, s in POLICY.items()
        if name != "viewer"
    }
    try:
        return {**await viewer.export(limit), "policy": policy}
    except Exception as exc:  # noqa: BLE001 - memory down: empty graph, not an error page
        return {"nodes": [], "edges": [], "policy": policy, "error": str(exc)}


@app.get("/api/agents")
async def agents() -> dict[str, Any]:
    out = []
    for name, (url, _) in PEERS.items():
        try:
            card = await a2a.card(url)
            out.append(
                {
                    "name": name,
                    "up": True,
                    "description": card.description,
                    "skills": [{"id": s.id, "name": s.name} for s in card.skills],
                }
            )
        except Exception:  # noqa: BLE001 - an agent down shows as down
            a2a._cards.pop(url, None)
            out.append({"name": name, "up": False, "description": "", "skills": []})
    return {"agents": out, "tiers": {str(int(t)): ledger.counts[t] for t in Tier}}


@app.get("/api/audit")
async def audit(n: int = 60) -> dict[str, Any]:
    if not AUDIT.exists():
        return {"entries": []}
    with AUDIT.open(encoding="utf-8") as f:  # noqa: ASYNC230 - a 60-line tail of a local file
        tail = deque(f, maxlen=n)
    return {"entries": [json.loads(x) for x in reversed(tail) if x.strip()]}


# ---------------- the built web UI, if present ----------------

UI_DIST = Path(os.environ.get("UI_DIST", "ui/dist"))
if (UI_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        f = (UI_DIST / path).resolve()
        if path and f.is_file() and UI_DIST.resolve() in f.parents:
            return FileResponse(f)
        # index.html must not be cached: a rebuild changes which asset bundle it points at
        return FileResponse(UI_DIST / "index.html", headers={"Cache-Control": "no-cache"})
