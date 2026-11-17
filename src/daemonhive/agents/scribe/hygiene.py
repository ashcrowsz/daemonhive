"""Scribe: nightly memory hygiene (runs as a Kubernetes CronJob).

- merge entities that are the same thing spelled differently
- close the validity interval of facts superseded by newer ones
Facts are never deleted: "weight was 82 kg" stays true for the period it was true.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date

from daemonhive.agents.fitness.parser import normalize_name


def entity_key(name: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-z0-9 ]", " ", ascii_.lower())
    return normalize_name(" ".join(cleaned.split()))


def merge_candidates(names: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(entity_key(n), []).append(n)
    return {k: sorted(v) for k, v in groups.items() if len(v) > 1}


@dataclass(frozen=True)
class Fact:
    subject: str
    relation: str
    value: str
    valid_from: date
    valid_to: date | None = None


SINGLE_VALUED = {"HAS_WEIGHT", "HAS_GOAL", "WORKS_ON_PRIMARY"}


def invalidate_superseded(facts: list[Fact]) -> list[Fact]:
    """For single-valued relations, each fact ends where the next one starts."""
    out: list[Fact] = []
    by_key: dict[tuple[str, str], list[Fact]] = {}
    for f in facts:
        if f.relation in SINGLE_VALUED:
            by_key.setdefault((f.subject, f.relation), []).append(f)
        else:
            out.append(f)
    for group in by_key.values():
        group.sort(key=lambda f: f.valid_from)
        for cur, nxt in itertools.pairwise(group):
            out.append(cur if cur.valid_to else replace(cur, valid_to=nxt.valid_from))
        out.append(group[-1])
    return out


def value_at(facts: list[Fact], subject: str, relation: str, day: date) -> str | None:
    for f in facts:
        same = f.subject == subject and f.relation == relation
        if same and f.valid_from <= day and (f.valid_to is None or day < f.valid_to):
            return f.value
    return None
