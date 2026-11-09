"""Offline scenario harness: real agent logic, fake peers/stores/LLM.

Each scenario asserts on three things:
  trajectory  - which hops happened (parse, MCP, A2A, model tier)
  end state   - which facts landed in memory
  message     - what the user would read (checked loosely offline, by LLM judge in CI)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from daemonhive.agents.fitness.agent import FitnessAgent, Outcome
from daemonhive.agents.fitness.parser import Session, parse_session
from daemonhive.agents.wellbeing.recovery import MealRow, SleepRow, recovery_summary
from daemonhive.common.a2a import TaskResult, TaskState
from daemonhive.common.tiers import Tier
from daemonhive.mcp.permissions import Guard


@dataclass
class FakeStore:
    sessions: list[Session] = field(default_factory=list)

    async def log_session(self, s: Session) -> int:
        self.sessions.append(s)
        return len(self.sessions)

    async def last_session(self, kind: str, before: date) -> Session | None:
        prior = [s for s in self.sessions if s.kind == kind and s.day < before]
        return max(prior, key=lambda s: s.day) if prior else None


@dataclass
class FakeMemory:
    guard: Guard = field(default_factory=Guard)
    facts: list[tuple[str, str, str]] = field(default_factory=list)

    async def add_fact(self, source: str, subject: str, relation: str, obj: str,
                       valid_from: str, props: dict[str, Any]) -> None:
        self.guard.check_write(source, subject, relation, obj)
        self.facts.append((subject, relation, obj))


@dataclass
class FakeWellbeing:
    sleep: list[SleepRow]
    meals: list[MealRow]
    online: bool = True
    kcal_target: int = 2800

    async def send(self, base_url: str, skill: str, payload: dict[str, Any]) -> TaskResult:
        if not self.online:
            return TaskResult(id="t", state=TaskState.failed, error="unreachable")
        out = recovery_summary(self.sleep, self.meals, until=date.fromisoformat(payload["until"]),
                               days=payload["days"], kcal_target=self.kcal_target)
        return TaskResult(id="t", state=TaskState.completed, output=out)


class EchoWriter:
    """Stands in for the tier-2 model: returns the prompt so tests can inspect it."""

    async def ask(self, system: str, user: str, tier: Tier = Tier.large, max_tokens: int = 600) -> str:
        return user


async def run_fitness(history: list[str], log: str, wellbeing: FakeWellbeing) -> tuple[Outcome, FakeMemory]:
    store, memory = FakeStore(), FakeMemory()
    for h in history:
        store.sessions.append(parse_session(h))
    agent = FitnessAgent(store, memory, wellbeing, EchoWriter(), wellbeing_url="http://wellbeing")
    return await agent.handle_log(log), memory
