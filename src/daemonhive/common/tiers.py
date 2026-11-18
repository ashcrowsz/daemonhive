"""Tiered model routing: spend tokens only where code can't do the job.

tier 0: code / regex (free, instant)
tier 1: small model (routing, short classifications)
tier 2: bigger model, for cross-domain reasoning and the messages you read

Model names are LiteLLM aliases; deploy/litellm*.yaml decides what's behind them
(LM Studio on your machine, or a hosted model).
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum


class Tier(IntEnum):
    code = 0
    small = 1
    large = 2


TIER_MODELS = {
    Tier.small: os.environ.get("HIVE_MODEL_SMALL", "hive-small"),
    Tier.large: os.environ.get("HIVE_MODEL_LARGE", "hive-large"),
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
