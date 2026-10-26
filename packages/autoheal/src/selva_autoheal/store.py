"""Incident state in Redis: dedup, cooldown, flap protection, daily counters,
the kill switch and the work queue.

Keys (all under ``selva:autoheal:``):

- ``kill``                     — present ⇒ the agent stops; intake still records.
- ``cooldown:<key>``           — SET NX EX: a group re-notified inside the
  cooldown is a duplicate (Alertmanager repeats every ``repeat_interval``).
- ``runs:<key>:<day>``         — diagnoses of one incident key per UTC day; above
  the limit the key is ``flapping`` and is not diagnosed again that day.
- ``incidents:<day>``          — incidents queued per UTC day.
- ``spend:<day>``              — USD the agent spent per UTC day (cost-model
  estimate, the same one the grant meter uses).
- ``record:<key>``             — the latest incident record (JSON, 30 days).
- ``queue``                    — incidents waiting for the agent (LPUSH/RPOP).

The queue is at-most-once: an incident popped by a worker that then dies is
not retried; the alert's next notification after the cooldown re-queues it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from .alerts import IncidentSignal
from .config import AutohealConfig

PREFIX = "selva:autoheal:"
KILL_KEY = PREFIX + "kill"
QUEUE_KEY = PREFIX + "queue"
RECORD_TTL_SECONDS = 30 * 24 * 3600
DAY_TTL_SECONDS = 2 * 24 * 3600

Decision = Literal["queued", "duplicate", "flapping", "daily_limit", "killed", "resolved"]


def _day(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y%m%d")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


@dataclass(frozen=True)
class AdmitResult:
    key: str
    decision: Decision


class IncidentStore:
    """Redis-backed. ``redis`` is a ``redis.asyncio.Redis`` (or fakeredis)."""

    def __init__(self, redis: Any, cfg: AutohealConfig) -> None:
        self._r = redis
        self._cfg = cfg

    # -- kill switch -------------------------------------------------------

    async def killed(self) -> bool:
        return bool(await self._r.exists(KILL_KEY))

    # -- intake ------------------------------------------------------------

    async def admit(self, signal: IncidentSignal, now: datetime) -> AdmitResult:
        """Decide what one qualifying notification does, and queue it if new."""
        key = signal.key
        if await self.killed():
            await self._save(key, signal, "killed", now)
            return AdmitResult(key, "killed")
        fresh = await self._r.set(
            f"{PREFIX}cooldown:{key}", "1", nx=True, ex=max(1, self._cfg.cooldown_seconds)
        )
        if not fresh:
            return AdmitResult(key, "duplicate")
        day = _day(now)
        runs_key = f"{PREFIX}runs:{key}:{day}"
        runs = int(await self._r.incr(runs_key))
        await self._r.expire(runs_key, DAY_TTL_SECONDS)
        if runs > self._cfg.max_runs_per_key_per_day:
            await self._save(key, signal, "flapping", now)
            return AdmitResult(key, "flapping")
        count_key = f"{PREFIX}incidents:{day}"
        count = int(await self._r.incr(count_key))
        await self._r.expire(count_key, DAY_TTL_SECONDS)
        if count > self._cfg.max_incidents_per_day:
            await self._save(key, signal, "daily_limit", now)
            return AdmitResult(key, "daily_limit")
        await self._save(key, signal, "queued", now)
        await self._r.lpush(QUEUE_KEY, json.dumps(signal.to_dict()))
        return AdmitResult(key, "queued")

    async def resolve(self, signal: IncidentSignal, now: datetime) -> AdmitResult:
        """A resolved notification: record it; nothing is queued."""
        record = await self.record(signal.key)
        if record is not None:
            record["state"] = "resolved"
            record["resolved_at"] = now.isoformat()
            await self.put_record(signal.key, record)
        return AdmitResult(signal.key, "resolved")

    async def _save(self, key: str, signal: IncidentSignal, state: str, now: datetime) -> None:
        record = await self.record(key) or {"key": key, "first_seen": now.isoformat()}
        record.update(
            {
                "state": state,
                "last_seen": now.isoformat(),
                "alertname": signal.alertname,
                "namespace": signal.namespace,
            }
        )
        await self.put_record(key, record)

    # -- records -----------------------------------------------------------

    async def record(self, key: str) -> dict[str, Any] | None:
        raw = _text(await self._r.get(f"{PREFIX}record:{key}"))
        return json.loads(raw) if raw else None

    async def put_record(self, key: str, record: dict[str, Any]) -> None:
        await self._r.set(
            f"{PREFIX}record:{key}", json.dumps(record, default=str), ex=RECORD_TTL_SECONDS
        )

    # -- queue -------------------------------------------------------------

    async def pop(self) -> IncidentSignal | None:
        raw = _text(await self._r.rpop(QUEUE_KEY))
        return IncidentSignal.from_dict(json.loads(raw)) if raw else None

    # -- spend -------------------------------------------------------------

    async def spend_today(self, now: datetime) -> float:
        raw = _text(await self._r.get(f"{PREFIX}spend:{_day(now)}"))
        return float(raw) if raw else 0.0

    async def add_spend(self, usd: float, now: datetime) -> float:
        key = f"{PREFIX}spend:{_day(now)}"
        total = float(await self._r.incrbyfloat(key, round(max(usd, 0.0), 6)))
        await self._r.expire(key, DAY_TTL_SECONDS)
        return total
