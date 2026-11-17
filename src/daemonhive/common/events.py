"""NATS subjects and an idempotent consumer.

JetStream delivers at least once. Handlers must therefore be idempotent: we key
every event and skip ones we've already processed.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

WORKOUT_LOGGED = "hive.workout.logged"
SLEEP_LOGGED = "hive.sleep.logged"
MEAL_LOGGED = "hive.meal.logged"
TASK_DUE = "hive.task.due"
DEAD_LETTER = "hive.dlq"


class Event(BaseModel):
    id: str  # idempotency key, e.g. "workout:2026-11-03:push"
    subject: str
    source: str
    data: dict[str, Any]

    def encode(self) -> bytes:
        return self.model_dump_json().encode()

    @classmethod
    def decode(cls, raw: bytes) -> Event:
        return cls.model_validate(json.loads(raw))


class SeenSet:
    """Bounded LRU of processed event ids (Postgres-backed in prod)."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.maxsize = maxsize

    def add_if_new(self, key: str) -> bool:
        if key in self._seen:
            self._seen.move_to_end(key)
            return False
        self._seen[key] = None
        if len(self._seen) > self.maxsize:
            self._seen.popitem(last=False)
        return True

    def forget(self, key: str) -> None:
        self._seen.pop(key, None)


async def handle_once(
    event: Event,
    seen: SeenSet,
    handler: Callable[[Event], Awaitable[None]],
    *,
    max_attempts: int,
    attempt: int,
    dead_letter: Callable[[Event, str], Awaitable[None]],
) -> str:
    if not seen.add_if_new(event.id):
        return "duplicate"
    try:
        await handler(event)
        return "ok"
    except Exception as exc:  # noqa: BLE001 - any handler failure means retry or dead-letter
        seen.forget(event.id)  # allow redelivery to retry
        if attempt >= max_attempts:
            await dead_letter(event, str(exc))
            return "dead_lettered"
        return "retry"
