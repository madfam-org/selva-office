"""Alertmanager notification → incident decision. Used by the nexus-api route.

One notification is one alert group. The intake never calls a model and
never reaches Enclii: it validates, normalises, qualifies, and lets the store
decide (queued / duplicate / flapping / daily_limit / killed / resolved).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from .alerts import AlertmanagerWebhook, normalise, qualify
from .config import AutohealConfig
from .store import IncidentStore


class InvalidPayload(ValueError):
    pass


@dataclass(frozen=True)
class IntakeResult:
    incident_key: str
    decision: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"incident_key": self.incident_key, "decision": self.decision,
                "reason": self.reason}


async def handle(
    body: Any, store: IncidentStore, cfg: AutohealConfig, now: datetime
) -> IntakeResult:
    try:
        payload = AlertmanagerWebhook.model_validate(body)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        raise InvalidPayload(f"invalid Alertmanager payload: {', '.join(fields)[:300]}") from exc
    signal = normalise(payload)
    if signal.status == "resolved":
        result = await store.resolve(signal, now)
        return IntakeResult(signal.key, result.decision, "resolved")
    q = qualify(signal, cfg)
    if not q.qualifies:
        return IntakeResult(signal.key, "ignored", q.reason)
    result = await store.admit(signal, now)
    return IntakeResult(signal.key, result.decision, q.reason)
