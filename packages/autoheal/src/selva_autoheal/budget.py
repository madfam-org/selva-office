"""Per-incident and per-day USD caps for the agent, checked BEFORE each call.

These caps live inside the provider grant (``madfam_inference.grants``),
which stays the hard ceiling for the credential: the grant guard refuses a
call past the grant, and this module refuses a call past the incident or the
day. Both use the same cost model, so they agree on what a call costs.

A call is admitted only if its *worst case* (estimated input tokens plus the
full ``max_tokens`` of output) fits under both remaining caps; after the call
the actual cost is charged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

#: ``price(provider, model, input_tokens, output_tokens) -> usd``
PriceFn = Callable[[str, str, int, int], float]

CHARS_PER_TOKEN = 3  # conservative, as in madfam_inference.grants


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class IncidentBudget:
    cap_usd: float
    daily_cap_usd: float
    spent_today_usd: float
    price: PriceFn
    spent_usd: float = 0.0
    calls: int = 0
    log: list[dict[str, object]] = field(default_factory=list)

    def worst_case(self, provider: str, model: str, prompt_chars: int, max_tokens: int) -> float:
        return float(self.price(provider, model, prompt_chars // CHARS_PER_TOKEN + 1, max_tokens))

    def admit(self, provider: str, model: str, prompt_chars: int, max_tokens: int) -> float:
        """Raise ``BudgetExceeded`` unless one more call fits. Returns its worst case."""
        worst = self.worst_case(provider, model, prompt_chars, max_tokens)
        if self.spent_usd + worst > self.cap_usd:
            raise BudgetExceeded("incident_cap")
        if self.spent_today_usd + self.spent_usd + worst > self.daily_cap_usd:
            raise BudgetExceeded("daily_cap")
        return worst

    def charge(self, provider: str, model: str, usd: float, at: datetime) -> None:
        self.spent_usd = round(self.spent_usd + max(usd, 0.0), 6)
        self.calls += 1
        self.log.append(
            {"at": at.isoformat(), "provider": provider, "model": model, "usd": round(usd, 6)}
        )
