from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from daemonhive.common.a2a import A2AServer, AgentCard, Skill, TaskRequest


def make_client() -> TestClient:
    card = AgentCard(name="echo", description="echo agent", url="http://echo",
                     skills=[Skill(id="echo", name="Echo", description="returns input")])
    server = A2AServer(card, tokens={"tok-fitness": "fitness", "tok-work": "work"})

    @server.skill("echo", allowed_callers={"fitness"})
    async def echo(req: TaskRequest) -> dict[str, Any]:
        if req.input.get("boom"):
            raise RuntimeError("kaboom")
        return {"echo": req.input}

    app = FastAPI()
    server.mount(app)
    return TestClient(app)


def call(c: TestClient, token: str, caller: str, skill: str = "echo", **inp: Any) -> Any:
    return c.post("/a2a/tasks", headers={"Authorization": f"Bearer {token}"},
                  json={"skill": skill, "caller": caller, "input": inp})


def test_agent_card_is_published() -> None:
    card = make_client().get("/.well-known/agent-card.json").json()
    assert card["name"] == "echo" and card["skills"][0]["id"] == "echo"
    assert card["security_schemes"]["bearer"]["scheme"] == "bearer"


def test_allowed_caller_gets_result() -> None:
    r = call(make_client(), "tok-fitness", "fitness", x=1).json()
    assert r["state"] == "completed" and r["output"] == {"echo": {"x": 1}}


def test_bad_token_or_spoofed_caller_is_401() -> None:
    c = make_client()
    assert call(c, "nope", "fitness").status_code == 401
    assert call(c, "tok-work", "fitness").status_code == 401  # token belongs to work


def test_caller_not_in_allowlist_is_rejected() -> None:
    assert call(make_client(), "tok-work", "work").json()["state"] == "rejected"


def test_handler_failure_is_reported_not_raised() -> None:
    r = call(make_client(), "tok-fitness", "fitness", boom=True).json()
    assert r["state"] == "failed" and "kaboom" in r["error"]


def test_undeclared_skill_cannot_be_registered() -> None:
    card = AgentCard(name="a", description="a", url="u", skills=[])
    with pytest.raises(ValueError):
        A2AServer(card, tokens={}).skill("ghost", allowed_callers=set())
