"""Tiered model routing: spend tokens only where code can't do the job.

tier 0: code / regex (free, instant)
tier 1: small local model via Ollama, or the cheapest hosted one
tier 2: strong hosted model, for cross-domain reasoning and the messages you read
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum


class Tier(IntEnum):
    code = 0
    small = 1
    large = 2


TIER_MODELS = {
    Tier.small: "ollama/qwen3:4b",
    Tier.large: "claude-sonnet-5-5",
}


@dataclass
class TierLedger:
    """Counts which tier handled each event: the 'share without an LLM' metric."""

    counts: Counter[Tier] = field(default_factory=Counter)

    def record(self, tier: Tier) -> None:
        self.counts[tier] += 1

    def share(self, tier: Tier) -> float:
        total = sum(self.counts.values())
        return self.counts[tier] / total if total else 0.0
