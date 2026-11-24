"""A minimal A2A (agent-to-agent) implementation.

Each agent publishes an Agent Card at /.well-known/agent-card.json describing
its skills. Other agents send it tasks; the callee stays a black box with its
own tools and its own database. That is the whole difference with MCP:
MCP = agent -> tools/data, A2A = agent -> another agent.

This covers the subset Daemonhive needs (sync tasks, JSON parts, bearer auth).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from daemonhive.common.tracing import continue_trace, trace_headers, traceable


class Skill(BaseModel):
    id: str
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    examples: list[str] = Field(default_factory=list)


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    protocol_version: str = "0.3"
    capabilities: dict[str, bool] = Field(default_factory=lambda: {"streaming": False})
    default_input_modes: list[str] = Field(
        default_factory=lambda: ["application/json", "text/plain"]
    )
    default_output_modes: list[str] = Field(
        default_factory=lambda: ["application/json", "text/plain"]
    )
    security_schemes: dict[str, Any] = Field(
        default_factory=lambda: {"bearer": {"type": "http", "scheme": "bearer"}}
    )
    skills: list[Skill]

    def skill(self, skill_id: str) -> Skill | None:
        return next((s for s in self.skills if s.id == skill_id), None)


class TaskState(str, Enum):
    submitted = "submitted"
    working = "working"
    completed = "completed"
    failed = "failed"
    rejected = "rejected"


class TaskRequest(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    skill: str
    input: dict[str, Any] = Field(default_factory=dict)
    caller: str


class TaskResult(BaseModel):
    id: str
    state: TaskState
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


Handler = Callable[[TaskRequest], Awaitable[dict[str, Any]]]


class A2AServer:
    """Wires an AgentCard + skill handlers onto a FastAPI app."""

    def __init__(self, card: AgentCard, tokens: dict[str, str]) -> None:
        self.card = card
        self.tokens = tokens  # token -> caller agent name
        self.handlers: dict[str, Handler] = {}
        self.allowed_callers: dict[str, set[str]] = {}

    def skill(self, skill_id: str, allowed_callers: set[str]) -> Callable[[Handler], Handler]:
        if self.card.skill(skill_id) is None:
            raise ValueError(f"skill {skill_id!r} not declared on the agent card")

        def register(fn: Handler) -> Handler:
            self.handlers[skill_id] = fn
            self.allowed_callers[skill_id] = allowed_callers
            return fn

        return register

    def mount(self, app: FastAPI) -> None:
        @app.get("/.well-known/agent-card.json")
        async def agent_card() -> dict[str, Any]:
            return self.card.model_dump()

        @app.post("/a2a/tasks")
        async def run_task(
            req: TaskRequest, request: Request, authorization: str = Header("")
        ) -> TaskResult:
            caller = self.tokens.get(authorization.removeprefix("Bearer ").strip())
            if caller is None or caller != req.caller:
                raise HTTPException(401, "unknown caller")
            handler = self.handlers.get(req.skill)
            if handler is None:
                return TaskResult(id=req.id, state=TaskState.rejected, error="unknown skill")
            if caller not in self.allowed_callers[req.skill]:
                return TaskResult(id=req.id, state=TaskState.rejected, error="caller not allowed")
            # the caller's trace continues here: this skill becomes a child span of its hop
            span = traceable(
                run_type="chain",
                name=f"{self.card.name}.{req.skill}",
                metadata={"agent": self.card.name, "skill": req.skill, "caller": caller},
            )(handler)
            try:
                with continue_trace(request.headers):
                    output = await span(req)
                return TaskResult(id=req.id, state=TaskState.completed, output=output)
            except Exception as exc:  # noqa: BLE001 - the callee's failure is data for the caller
                return TaskResult(id=req.id, state=TaskState.failed, error=str(exc))


class A2AClient:
    def __init__(self, me: str, token: str, timeout: float = 10.0) -> None:
        self.me = me
        self.token = token
        self.timeout = timeout
        self._cards: dict[str, AgentCard] = {}

    async def card(self, base_url: str) -> AgentCard:
        if base_url not in self._cards:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.get(f"{base_url}/.well-known/agent-card.json")
                r.raise_for_status()
                self._cards[base_url] = AgentCard.model_validate(r.json())
        return self._cards[base_url]

    async def send(self, base_url: str, skill: str, payload: dict[str, Any]) -> TaskResult:
        req = TaskRequest(skill=skill, input=payload, caller=self.me)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(
                    f"{base_url}/a2a/tasks",
                    json=req.model_dump(),
                    headers={"Authorization": f"Bearer {self.token}", **trace_headers()},
                )
                r.raise_for_status()
                return TaskResult.model_validate(r.json())
        except httpx.HTTPError as exc:
            # peer down or slow: callers must degrade, not crash
            return TaskResult(id=req.id, state=TaskState.failed, error=f"unreachable: {exc}")
