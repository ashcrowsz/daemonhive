"""Per-agent scopes on the shared memory, enforced server-side, with an audit log.

Fitness may write Session/Exercise facts and AFFECTED_BY edges; it may read
recovery flags. It may never write Habit or Project entities. The MCP server
checks this on every call: the agent's prompt is not a security boundary.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


class PermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Scope:
    read: frozenset[str]
    write_entities: frozenset[str]
    write_relations: frozenset[str]


POLICY: dict[str, Scope] = {
    "fitness": Scope(
        read=frozenset({"Session", "Exercise", "Injury", "SleepDeficit", "CalorieDeficit"}),
        write_entities=frozenset({"Session", "Exercise", "Injury"}),
        write_relations=frozenset({"PERFORMED", "AFFECTED_BY", "HIT_PR"}),
    ),
    "wellbeing": Scope(
        read=frozenset({"Habit", "SleepDeficit", "CalorieDeficit", "Person", "Weight", "Phase"}),
        write_entities=frozenset({"Person", "Habit", "SleepDeficit", "CalorieDeficit"}),
        write_relations=frozenset({"HAS_WEIGHT", "HAS_HABIT", "IN_PHASE"}),
    ),
    "work": Scope(
        read=frozenset({"Project", "Session", "SleepDeficit"}),
        write_entities=frozenset({"Project"}),
        write_relations=frozenset({"WORKS_ON", "WORKS_ON_PRIMARY"}),
    ),
    # the web UI: reads the whole graph, writes nothing
    "viewer": Scope(read=frozenset({"*"}), write_entities=frozenset(), write_relations=frozenset()),
    "scribe": Scope(
        read=frozenset({"*"}),
        write_entities=frozenset({"*"}),
        write_relations=frozenset({"*"}),
    ),
}


def entity_type(ref: str) -> str:
    """'Session:push:2026-11-03' -> 'Session'"""
    return ref.split(":", 1)[0]


@dataclass
class Guard:
    policy: dict[str, Scope] = field(default_factory=lambda: POLICY)
    audit_path: Path | None = None
    log: list[dict[str, object]] = field(default_factory=list)

    def _audit(self, agent: str, action: str, target: str, allowed: bool) -> None:
        entry = {
            "ts": time.time(),
            "agent": agent,
            "action": action,
            "target": target,
            "allowed": allowed,
        }
        self.log.append(entry)
        if self.audit_path:
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def _scope(self, agent: str) -> Scope:
        scope = self.policy.get(agent)
        if scope is None:
            raise PermissionDenied(f"unknown agent {agent!r}")
        return scope

    def check_write(self, agent: str, subject: str, relation: str, obj: str) -> None:
        s = self._scope(agent)
        ok = ("*" in s.write_entities or entity_type(subject) in s.write_entities) and (
            "*" in s.write_relations or relation in s.write_relations
        )
        self._audit(agent, f"write:{relation}", f"{subject}->{obj}", ok)
        if not ok:
            raise PermissionDenied(f"{agent} may not write {relation} on {entity_type(subject)}")

    def check_read(self, agent: str, etype: str) -> None:
        s = self._scope(agent)
        ok = "*" in s.read or etype in s.read
        self._audit(agent, "read", etype, ok)
        if not ok:
            raise PermissionDenied(f"{agent} may not read {etype}")
