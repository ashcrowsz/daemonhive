"""Fitness agent: the reference scenario lives here.

log -> parse (tier 0) -> store (MCP) -> compare (tier 0)
    -> if regression: ask Well-being over A2A -> write fact to memory (MCP)
    -> write the message you read (tier 2)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from daemonhive.agents.fitness.analysis import LiftDelta, compare, describe, regressions
from daemonhive.agents.fitness.parser import ParseError, Session, parse_session
from daemonhive.common.a2a import TaskResult, TaskState
from daemonhive.common.tiers import Tier, TierLedger

MESSAGE_SYSTEM = """You are the Fitness agent in a personal assistant. Write ONE short
Telegram message (max 3 sentences). State the numbers plainly, connect them to
recovery data if given, and end with one honest question. No hype, no emojis spam."""


class FitnessStore(Protocol):
    async def log_session(self, s: Session) -> int: ...
    async def last_session(self, kind: str, before: Any) -> Session | None: ...


class Memory(Protocol):
    async def add_fact(self, source: str, subject: str, relation: str, obj: str,
                       valid_from: str, props: dict[str, Any]) -> None: ...


class Peer(Protocol):
    async def send(self, base_url: str, skill: str, payload: dict[str, Any]) -> TaskResult: ...


class Writer(Protocol):
    async def ask(self, system: str, user: str, tier: Tier = Tier.large,
                  max_tokens: int = 600) -> str: ...


@dataclass
class Outcome:
    message: str
    deltas: list[LiftDelta]
    recovery: dict[str, Any] | None = None
    trace: list[str] = field(default_factory=list)


class FitnessAgent:
    def __init__(self, store: FitnessStore, memory: Memory, peer: Peer, writer: Writer,
                 wellbeing_url: str, ledger: TierLedger | None = None) -> None:
        self.store, self.memory, self.peer, self.writer = store, memory, peer, writer
        self.wellbeing_url = wellbeing_url
        self.ledger = ledger or TierLedger()

    async def handle_log(self, text: str) -> Outcome:
        trace: list[str] = []
        try:
            session = parse_session(text)
        except ParseError as e:
            self.ledger.record(Tier.code)
            return Outcome(f"Couldn't parse that log: {e}", [], trace=["parse:error"])
        trace.append(f"parse:ok:{len(session.exercises)} exercises")

        previous = await self.store.last_session(session.kind, before=session.day)
        await self.store.log_session(session)
        trace.append("mcp:fitness-db.log_session")

        deltas = compare(previous, session)
        bad = regressions(deltas)
        if not bad:
            self.ledger.record(Tier.code)
            lines = [describe(d) for d in deltas if d.signal.value in ("pr", "regression")]
            msg = "Logged. " + ("; ".join(lines) if lines else "Nothing unusual vs last time.")
            return Outcome(msg, deltas, trace=[*trace, "tier0:reply"])

        recovery = await self._ask_recovery(session, trace)
        for d in bad:
            if recovery and recovery.get("flags"):
                for flag in recovery["flags"]:
                    await self.memory.add_fact(
                        source="fitness",
                        subject=f"Session:{session.kind}:{session.day}",
                        relation="AFFECTED_BY",
                        obj=flag,
                        valid_from=session.day.isoformat(),
                        props={"exercise": d.exercise, "volume_change": round(d.volume_change, 3)},
                    )
                trace.append("mcp:memory.add_fact")

        self.ledger.record(Tier.large)
        message = await self.writer.ask(MESSAGE_SYSTEM, self._prompt(bad, recovery, session))
        trace.append("tier2:message")
        return Outcome(message, deltas, recovery, trace)

    async def _ask_recovery(self, session: Session, trace: list[str]) -> dict[str, Any] | None:
        res = await self.peer.send(self.wellbeing_url, "recovery_summary",
                                   {"until": session.day.isoformat(), "days": 3})
        trace.append(f"a2a:wellbeing.recovery_summary:{res.state.value}")
        if res.state is not TaskState.completed:
            return None  # Well-being down: still report the regression, just without the why
        return res.output

    @staticmethod
    def _prompt(bad: list[LiftDelta], recovery: dict[str, Any] | None, s: Session) -> str:
        facts = "\n".join(
            f"- {d.exercise}: volume {d.volume_before:g} -> {d.volume_after:g} kg "
            f"({d.volume_change:+.0%}), top set {d.top_before:g} -> {d.top_after:g} kg"
            for d in bad
        )
        rec = (
            f"Recovery last 3 days: avg sleep {recovery['avg_sleep_h']} h, "
            f"calories {recovery['kcal_vs_target']:+d} kcal/day vs target, flags {recovery['flags']}"
            if recovery else "Recovery data unavailable (Well-being agent did not answer)."
        )
        notes = "; ".join(s.notes) or "none"
        return f"Session {s.kind} on {s.day}.\nRegressions:\n{facts}\n{rec}\nUser notes: {notes}"
