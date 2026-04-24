"""Financial circuit breaker — caps daily dollar exposure per org.

Implements Axiom II of the Swarm Governing Manifesto: "Our downside is
rigidly capped at 25%; our upside is exposed to infinity." The circuit
breaker ensures autonomous agents cannot exceed a configured daily dollar
limit, regardless of playbook permissions.

Uses Redis INCRBY + EXPIREAT for atomic, race-safe counter management.
Auto-resets at midnight UTC.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Default daily financial exposure limit per org (in USD cents)
DEFAULT_DAILY_LIMIT_CENTS = 5000  # $50.00


class FinancialCircuitBreaker:
    """Redis-backed daily financial exposure limiter.

    Each org has a counter that tracks cumulative dollar exposure for the
    current UTC day. When the limit is reached, all BILLING_WRITE actions
    are denied until midnight UTC reset.
    """

    def __init__(self, redis_client, daily_limit_cents: int = DEFAULT_DAILY_LIMIT_CENTS) -> None:
        self._redis = redis_client
        self._daily_limit_cents = daily_limit_cents

    def _key(self, org_id: str) -> str:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        return f"circuit:financial:{org_id}:{date_str}"

    def _seconds_until_midnight_utc(self) -> int:
        now = datetime.now(UTC)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        midnight_tomorrow = midnight.replace(day=midnight.day + 1) if midnight <= now else midnight
        return max(1, int((midnight_tomorrow - now).total_seconds()))

    async def check(self, org_id: str, amount_cents: int) -> bool:
        """Check if the financial exposure is within limits.

        Returns True if the amount can be spent, False if it would exceed the limit.
        Does NOT record the spend — call record() after successful execution.
        """
        key = self._key(org_id)
        try:
            current = await self._redis.get(key)
            current_cents = int(current) if current else 0
            return (current_cents + amount_cents) <= self._daily_limit_cents
        except Exception:
            # If Redis is down, fail-safe: deny financial actions
            logger.warning("Circuit breaker Redis check failed for org=%s, denying", org_id)
            return False

    async def record(self, org_id: str, amount_cents: int) -> int:
        """Record a financial exposure. Returns the new total for the day.

        Uses INCRBY for atomic increment + EXPIREAT for auto-reset at midnight.
        """
        key = self._key(org_id)
        try:
            new_total = await self._redis.incrby(key, amount_cents)
            ttl = await self._redis.ttl(key)
            if ttl < 0:
                # First write of the day — set expiry to midnight UTC
                await self._redis.expire(key, self._seconds_until_midnight_utc())
            return new_total
        except Exception:
            logger.warning("Circuit breaker Redis record failed for org=%s", org_id)
            return 0

    async def get_status(self, org_id: str) -> dict:
        """Get the current financial exposure status for an org."""
        key = self._key(org_id)
        try:
            current = await self._redis.get(key)
            current_cents = int(current) if current else 0
            return {
                "org_id": org_id,
                "used_cents": current_cents,
                "remaining_cents": max(0, self._daily_limit_cents - current_cents),
                "limit_cents": self._daily_limit_cents,
                "tripped": current_cents >= self._daily_limit_cents,
                "resets_at": datetime.now(UTC)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .isoformat()
                + "Z",
            }
        except Exception:
            return {
                "org_id": org_id,
                "used_cents": 0,
                "remaining_cents": 0,
                "limit_cents": self._daily_limit_cents,
                "tripped": True,  # fail-safe
                "error": "Redis unavailable",
            }
