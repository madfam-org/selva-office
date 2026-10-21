"""Provider credit grants: declared credit, a real-time meter, and a fail-closed guard.

A *grant* is prepaid provider credit with an amount, a window and a list of
orgs allowed to draw on it (contract C1, ``docs/PROVIDER_CREDIT_GRANTS.md``).
The grant itself is declared out of band (Vault property
``provider_grants_json`` → file ``PROVIDER_GRANTS_PATH``, or env
``PROVIDER_GRANTS_JSON``); this module never sees a key value, only the name
of the env var that holds it.

Three pieces:

* **Loader** — strict pydantic validation. A config that does not parse is
  treated as "no valid grant", never as "no limit".
* **Meter** — Redis counters per grant: settled ``spent`` USD, in-flight
  reservations that expire on their own (a dead pod cannot leak budget), and
  a 2-hour burn log. Check-and-reserve, settle and release are single Lua
  scripts, so N pods racing for the last dollar can never overshoot the
  ceiling (``amount_usd - safety_margin_usd``).
* **Guard** — ``PROVIDER_GRANTS_REQUIRED_FOR`` (comma list, e.g.
  ``anthropic``) names providers that may ONLY be used under a valid,
  started, unexpired, unexhausted grant whose ``allowed_orgs`` contains the
  request's org. Anything else — no grant, wrong org, expired, ceiling,
  invalid config, Redis down, cost model missing — makes the provider
  unavailable for that call. The router then continues its normal fallback
  chain; the guard can only remove options, never add them.

Nothing here runs unless a grant is declared or a provider is listed in
``PROVIDER_GRANTS_REQUIRED_FOR``: with neither, :func:`get_default_guard`
returns a guard whose ``enabled`` is False and the router behaves exactly as
before.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import math
import os
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .types import InferenceRequest

logger = logging.getLogger(__name__)

ENV_PATH = "PROVIDER_GRANTS_PATH"
ENV_JSON = "PROVIDER_GRANTS_JSON"
ENV_REQUIRED_FOR = "PROVIDER_GRANTS_REQUIRED_FOR"
ENV_REDIS_URL = "PROVIDER_GRANTS_REDIS_URL"
ENV_FALLBACK_REDIS_URL = "REDIS_URL"
ENV_RESERVATION_TTL = "PROVIDER_GRANTS_RESERVATION_TTL_SECONDS"
ENV_PLATFORM_ORG = "PLATFORM_ORG_ID"

#: Reservations expire on their own after this many seconds. It covers one
#: provider attempt (the Anthropic adapter's HTTP timeout is 120 s), so a pod
#: that dies mid-call frees its hold within ~2.5 minutes.
DEFAULT_RESERVATION_TTL_SECONDS = 150
#: Re-read the grants file at most this often (kubelet refreshes mounted
#: Secret files in place, so a Vault edit is picked up without a restart).
CONFIG_RECHECK_SECONDS = 60.0
#: Tokens assumed per image block when estimating the worst-case input.
IMAGE_TOKENS_ESTIMATE = 2000
#: Characters per token used for the input estimate. 3 (not the usual ~4)
#: over-estimates on purpose: a reservation must never be smaller than the
#: call it covers.
CHARS_PER_TOKEN = 3
BURN_WINDOW_SECONDS = 3600
BURN_LOG_RETENTION_SECONDS = 7200
_ERROR_LOG_INTERVAL_SECONDS = 60.0

#: Model-id prefixes per provider, used to recognise a caller-pinned model.
PROVIDER_MODEL_PREFIXES: dict[str, tuple[str, ...]] = {
    "anthropic": ("claude-", "anthropic."),
}

PaceStatus = Literal["behind", "on_pace", "ahead", "exhausted", "expired", "unknown"]


class GrantConfigError(ValueError):
    """The grants config could not be parsed or failed validation."""


class ProviderGrantUnavailableError(RuntimeError):
    """A caller-pinned model's provider is grant-guarded and unavailable.

    Raised instead of silently swapping the pinned model for another
    provider's. The message names the provider and the reason code; it never
    contains amounts or prompt content.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Config (contract C1)
# ─────────────────────────────────────────────────────────────────────────────


class ProviderGrant(BaseModel):
    """One declared provider credit grant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")
    provider: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    amount_usd: float = Field(gt=0)
    safety_margin_usd: float = Field(default=0.0, ge=0)
    starts_at: datetime
    expires_at: datetime
    allowed_orgs: list[str] = Field(min_length=1)
    pacing: Literal["use_it_or_lose_it", "steady", "reserve"] = "use_it_or_lose_it"
    autopilot: bool = False
    notes: str = ""

    @field_validator("starts_at", "expires_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must carry a timezone (e.g. ...Z)")
        return value.astimezone(UTC)

    @field_validator("allowed_orgs")
    @classmethod
    def _orgs(cls, value: list[str]) -> list[str]:
        cleaned = [org.strip() for org in value]
        if any(not org for org in cleaned):
            raise ValueError("allowed_orgs entries must be non-empty strings")
        return cleaned

    @model_validator(mode="after")
    def _window_and_margin(self) -> ProviderGrant:
        if self.expires_at <= self.starts_at:
            raise ValueError("expires_at must be after starts_at")
        if self.safety_margin_usd >= self.amount_usd:
            raise ValueError("safety_margin_usd must be smaller than amount_usd")
        return self

    @property
    def ceiling_usd(self) -> float:
        return round(self.amount_usd - self.safety_margin_usd, 6)

    def is_active(self, now: datetime) -> bool:
        return self.starts_at <= now < self.expires_at


class GrantBook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grants: list[ProviderGrant] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> GrantBook:
        ids = [g.id for g in self.grants]
        if len(ids) != len(set(ids)):
            raise ValueError("grant ids must be unique")
        return self


def parse_grants(text: str, *, source: str = "<inline>") -> GrantBook:
    """Parse a grants document (JSON, or YAML when PyYAML is installed)."""
    stripped = text.strip()
    if not stripped:
        return GrantBook()
    data: Any
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as json_exc:
        try:
            import yaml
        except ImportError as exc:
            raise GrantConfigError(f"{source}: not valid JSON and PyYAML is not installed") from exc
        try:
            data = yaml.safe_load(stripped)
        except yaml.YAMLError:
            raise GrantConfigError(f"{source}: neither valid JSON nor YAML") from json_exc
    if not isinstance(data, dict):
        raise GrantConfigError(f"{source}: top level must be an object with a 'grants' list")
    try:
        return GrantBook.model_validate(data)
    except ValidationError as exc:
        # Field locations only — never echo input values (they may be private).
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise GrantConfigError(f"{source}: {problems}") from None


@dataclass(frozen=True)
class GrantConfigState:
    """Result of loading the grants config. ``error`` set ⇒ fail closed."""

    grants: tuple[ProviderGrant, ...] = ()
    error: str | None = None
    source: str = "none"


def load_grant_config(env: dict[str, str] | None = None) -> GrantConfigState:
    """Load grants from ``PROVIDER_GRANTS_PATH`` (preferred) or ``PROVIDER_GRANTS_JSON``.

    A configured path whose file does not exist means "no grants" (the
    Secret is mounted ``optional: true`` and may not be seeded yet). A file
    or env value that does not validate is an *error*: no grant applies.
    """
    env = dict(os.environ) if env is None else env
    path = (env.get(ENV_PATH) or "").strip()
    if path:
        p = Path(path)
        if p.is_file():
            try:
                book = parse_grants(p.read_text(encoding="utf-8"), source=path)
            except (GrantConfigError, OSError, UnicodeDecodeError) as exc:
                return GrantConfigState(error=str(exc), source=path)
            return GrantConfigState(grants=tuple(book.grants), source=path)
    inline = env.get(ENV_JSON) or ""
    if inline.strip():
        try:
            book = parse_grants(inline, source=ENV_JSON)
        except GrantConfigError as exc:
            return GrantConfigState(error=str(exc), source=ENV_JSON)
        return GrantConfigState(grants=tuple(book.grants), source=ENV_JSON)
    return GrantConfigState(source=path or "none")


def required_providers(env: dict[str, str] | None = None) -> frozenset[str]:
    env = dict(os.environ) if env is None else env
    raw = env.get(ENV_REQUIRED_FOR) or ""
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def platform_org_ids(env: dict[str, str] | None = None) -> frozenset[str]:
    """Org ids that mean "the platform operator" (``PLATFORM_ORG_ID``, default madfam)."""
    env = dict(os.environ) if env is None else env
    return frozenset({(env.get(ENV_PLATFORM_ORG) or "madfam").strip() or "madfam"})


def org_allowed(grant: ProviderGrant, org_id: str | None, platform_orgs: Iterable[str]) -> bool:
    """True when ``org_id`` may draw on ``grant``.

    Exact match against ``allowed_orgs`` (aliases such as a Janua org UUID are
    simply listed there). The platform org id (``PLATFORM_ORG_ID``) and the
    literal ``madfam`` are treated as one identity, so a grant that lists
    either admits both.
    """
    if not org_id:
        return False
    if org_id in grant.allowed_orgs:
        return True
    platform = set(platform_orgs) | {"madfam"}
    return org_id in platform and any(org in platform for org in grant.allowed_orgs)


# ─────────────────────────────────────────────────────────────────────────────
# Cost estimation (pricing lives in madfam_budget_gate.cost_model — C3)
# ─────────────────────────────────────────────────────────────────────────────


def _cost_fn() -> Callable[..., float] | None:
    try:
        from madfam_budget_gate.cost_model import estimate_cost
    except ImportError:
        return None
    return estimate_cost


def estimate_input_tokens(request: InferenceRequest) -> int:
    """Conservative input-token estimate (over-counts text, flat rate per image)."""
    chars = len(request.system_prompt or "")
    images = 0
    for msg in request.messages:
        content = msg.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    chars += len(str(block))
                elif block.get("type") in ("image_url", "image_base64", "image"):
                    images += 1
                else:
                    chars += len(json.dumps(block, default=str))
        elif content is not None:
            chars += len(json.dumps(content, default=str))
        chars += 16  # role + framing
    if request.tools:
        chars += len(json.dumps(request.tools, default=str))
    if request.response_format:
        chars += len(json.dumps(request.response_format, default=str))
    return math.ceil(chars / CHARS_PER_TOKEN) + images * IMAGE_TOKENS_ESTIMATE + 32


def worst_case_cost_usd(
    provider: str, model: str | None, request: InferenceRequest
) -> float | None:
    """Estimated input × input price + ``max_tokens`` × output price. None ⇒ no cost model."""
    fn = _cost_fn()
    if fn is None:
        return None
    return float(fn(provider, model, estimate_input_tokens(request), request.policy.max_tokens))


def actual_cost_usd(provider: str, model: str | None, usage: dict[str, Any]) -> float | None:
    """USD for a finished call from provider-reported usage. None ⇒ no cost model."""
    fn = _cost_fn()
    if fn is None:
        return None
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens") or 0)
    cache_write = int(
        usage.get("cache_creation_input_tokens") or usage.get("cache_creation_tokens") or 0
    )
    params = inspect.signature(fn).parameters
    if "cache_read_tokens" in params and "cache_creation_tokens" in params:
        return float(
            fn(
                provider,
                model,
                input_tokens,
                output_tokens,
                cache_read_tokens=cache_read,
                cache_creation_tokens=cache_write,
            )
        )
    # Cost model without cache rates: bill cache reads at the input rate and
    # cache writes at 1.25× input — both over-count, which keeps the ceiling safe.
    effective_input = input_tokens + cache_read + math.ceil(cache_write * 1.25)
    return float(fn(provider, model, effective_input, output_tokens))


# ─────────────────────────────────────────────────────────────────────────────
# Meter (Redis + Lua)
# ─────────────────────────────────────────────────────────────────────────────

_RESERVE_LUA = """
local spent = redis.call('GET', KEYS[1])
if not spent then return {'seed', '0', '0'} end
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
for _, rid in ipairs(expired) do redis.call('HDEL', KEYS[3], rid) end
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
local reserved = 0
for _, v in ipairs(redis.call('HVALS', KEYS[3])) do reserved = reserved + tonumber(v) end
local amount = tonumber(ARGV[3])
if tonumber(spent) + reserved + amount > tonumber(ARGV[2]) then
  return {'deny', spent, tostring(reserved)}
end
redis.call('ZADD', KEYS[2], ARGV[5], ARGV[4])
redis.call('HSET', KEYS[3], ARGV[4], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[6])
redis.call('EXPIRE', KEYS[3], ARGV[6])
return {'ok', spent, tostring(reserved + amount)}
"""

_SETTLE_LUA = """
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('HDEL', KEYS[3], ARGV[1])
local new = redis.call('INCRBYFLOAT', KEYS[1], ARGV[2])
redis.call('ZADD', KEYS[4], ARGV[3], ARGV[1] .. ':' .. ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[4], '-inf', tostring(tonumber(ARGV[3]) - tonumber(ARGV[5])))
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[4], ARGV[4])
return tostring(new)
"""

_RELEASE_LUA = """
redis.call('ZREM', KEYS[2], ARGV[1])
return redis.call('HDEL', KEYS[3], ARGV[1])
"""

_READ_LUA = """
local spent = redis.call('GET', KEYS[1])
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
for _, rid in ipairs(expired) do redis.call('HDEL', KEYS[3], rid) end
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
local reserved = 0
for _, v in ipairs(redis.call('HVALS', KEYS[3])) do reserved = reserved + tonumber(v) end
local burn = 0
for _, m in ipairs(redis.call('ZRANGEBYSCORE', KEYS[4], ARGV[2], '+inf')) do
  local amt = string.match(m, ':([^:]+)$')
  if amt then burn = burn + tonumber(amt) end
end
return {spent or false, tostring(reserved), tostring(burn)}
"""

LedgerSeeder = Callable[[ProviderGrant], Awaitable[float]]


def _keys(grant_id: str) -> tuple[str, str, str, str]:
    # Hash tag keeps every key of one grant in one slot (Lua multi-key safe).
    base = f"selva:pgrant:{{{grant_id}}}"
    return f"{base}:spent", f"{base}:resv", f"{base}:resv_amt", f"{base}:burn"


def _key_ttl(grant: ProviderGrant, now: datetime) -> int:
    # Keep counters 30 days past expiry (status stays readable), at least 1 h.
    return max(3600, int((grant.expires_at - now).total_seconds()) + 30 * 86400)


def _to_str(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


@dataclass
class MeterSnapshot:
    spent_usd: float | None
    reserved_usd: float
    burn_usd_60m: float


class GrantMeter:
    """Redis-backed grant counters. Every mutation is one atomic Lua script."""

    def __init__(
        self,
        redis: Any,
        *,
        seeder: LedgerSeeder | None = None,
        reservation_ttl_seconds: int = DEFAULT_RESERVATION_TTL_SECONDS,
    ) -> None:
        self._redis = redis
        self._seeder = seeder
        self._ttl = max(1, int(reservation_ttl_seconds))
        self._reserve = redis.register_script(_RESERVE_LUA)
        self._settle = redis.register_script(_SETTLE_LUA)
        self._release = redis.register_script(_RELEASE_LUA)
        self._read = redis.register_script(_READ_LUA)

    @property
    def redis(self) -> Any:
        return self._redis

    def set_seeder(self, seeder: LedgerSeeder | None) -> None:
        self._seeder = seeder

    async def ensure_seeded(self, grant: ProviderGrant, now: datetime) -> None:
        """Seed ``spent`` from the ledger when the key is absent (cold start).

        No seeder registered (the ledger is not reachable from this process,
        e.g. workers) or a seeder failure seeds 0 and logs — it never blocks.
        ``SET NX`` means a concurrent seeder never clobbers a live counter.
        """
        spent_key = _keys(grant.id)[0]
        value = 0.0
        source = "zero (no ledger seeder in this process)"
        if self._seeder is not None:
            try:
                value = max(0.0, float(await asyncio.wait_for(self._seeder(grant), timeout=5.0)))
                source = "ledger"
            except Exception as exc:
                value = 0.0
                source = f"zero (ledger seed failed: {type(exc).__name__})"
        created = await self._redis.set(
            spent_key, repr(value), nx=True, ex=_key_ttl(grant, now)
        )
        if created:
            logger.warning(
                "provider grants: initialised meter for grant %s from %s", grant.id, source
            )

    async def try_reserve(
        self, grant: ProviderGrant, amount_usd: float, now: datetime
    ) -> tuple[bool, str | None]:
        """Atomically reserve ``amount_usd``. Returns ``(allowed, reservation_id)``."""
        spent_key, resv_key, amt_key, _ = _keys(grant.id)
        reservation_id = uuid.uuid4().hex
        ts = now.timestamp()
        for _attempt in range(2):
            result = await self._reserve(
                keys=[spent_key, resv_key, amt_key],
                args=[
                    repr(ts),
                    repr(grant.ceiling_usd),
                    repr(max(0.0, amount_usd)),
                    reservation_id,
                    repr(ts + self._ttl),
                    _key_ttl(grant, now),
                ],
            )
            verdict = _to_str(result[0])
            if verdict == "seed":
                await self.ensure_seeded(grant, now)
                continue
            if verdict == "ok":
                return True, reservation_id
            return False, None
        return False, None

    async def settle(
        self, grant: ProviderGrant, reservation_id: str, actual_usd: float, now: datetime
    ) -> None:
        spent_key, resv_key, amt_key, burn_key = _keys(grant.id)
        await self._settle(
            keys=[spent_key, resv_key, amt_key, burn_key],
            args=[
                reservation_id,
                repr(max(0.0, actual_usd)),
                repr(now.timestamp()),
                _key_ttl(grant, now),
                BURN_LOG_RETENTION_SECONDS,
            ],
        )

    async def release(self, grant: ProviderGrant, reservation_id: str) -> None:
        _, resv_key, amt_key, _ = _keys(grant.id)
        await self._release(keys=[_keys(grant.id)[0], resv_key, amt_key], args=[reservation_id])

    async def snapshot(self, grant: ProviderGrant, now: datetime) -> MeterSnapshot:
        spent_key, resv_key, amt_key, burn_key = _keys(grant.id)
        exists = await self._redis.exists(spent_key)
        if not exists:
            await self.ensure_seeded(grant, now)
        ts = now.timestamp()
        spent, reserved, burn = await self._read(
            keys=[spent_key, resv_key, amt_key, burn_key],
            args=[repr(ts), repr(ts - BURN_WINDOW_SECONDS)],
        )
        return MeterSnapshot(
            spent_usd=None if spent is None else float(_to_str(spent)),
            reserved_usd=float(_to_str(reserved)),
            burn_usd_60m=float(_to_str(burn)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Status (contract C2)
# ─────────────────────────────────────────────────────────────────────────────


class GrantStatus(BaseModel):
    """Grant status (contract C2). Amounts are private: platform-admin surfaces only."""

    id: str
    provider: str
    ceiling_usd: float
    spent_usd: float | None
    reserved_usd: float | None
    remaining_usd: float | None
    starts_at: datetime
    expires_at: datetime
    seconds_to_expiry: int
    burn_usd_per_hour_60m: float | None
    required_usd_per_hour: float | None
    pace_status: PaceStatus
    autopilot: bool
    #: ``starts_at <= now < expires_at``.
    active: bool
    #: False when the meter (Redis) could not be read — amount fields are None.
    meter_ok: bool


def pace_for(
    *,
    now: datetime,
    grant: ProviderGrant,
    remaining_usd: float | None,
    burn_usd_per_hour: float | None,
) -> tuple[PaceStatus, float | None]:
    """Return ``(pace_status, required_usd_per_hour)``.

    ``required`` = remaining / hours left (from ``starts_at`` when not started
    yet). Burn within ±10 % of required is ``on_pace``.
    """
    if now >= grant.expires_at:
        return "expired", 0.0
    if remaining_usd is None or burn_usd_per_hour is None:
        return "unknown", None
    if remaining_usd <= 1e-9:
        return "exhausted", 0.0
    start = max(now, grant.starts_at)
    hours_left = max((grant.expires_at - start).total_seconds() / 3600.0, 1e-6)
    required = remaining_usd / hours_left
    if burn_usd_per_hour < required * 0.9:
        return "behind", round(required, 6)
    if burn_usd_per_hour > required * 1.1:
        return "ahead", round(required, 6)
    return "on_pace", round(required, 6)


def build_status(
    grant: ProviderGrant, snap: MeterSnapshot | None, now: datetime
) -> GrantStatus:
    seconds_to_expiry = max(0, int((grant.expires_at - now).total_seconds()))
    if snap is None or snap.spent_usd is None:
        spent = reserved = remaining = burn = None
        meter_ok = False
    else:
        spent = round(snap.spent_usd, 6)
        reserved = round(snap.reserved_usd, 6)
        remaining = round(max(0.0, grant.ceiling_usd - spent - reserved), 6)
        burn = round(snap.burn_usd_60m, 6)
        meter_ok = True
    pace, required = pace_for(
        now=now, grant=grant, remaining_usd=remaining, burn_usd_per_hour=burn
    )
    return GrantStatus(
        id=grant.id,
        provider=grant.provider,
        ceiling_usd=grant.ceiling_usd,
        spent_usd=spent,
        reserved_usd=reserved,
        remaining_usd=remaining,
        starts_at=grant.starts_at,
        expires_at=grant.expires_at,
        seconds_to_expiry=seconds_to_expiry,
        burn_usd_per_hour_60m=burn,
        required_usd_per_hour=required,
        pace_status=pace,
        autopilot=grant.autopilot,
        active=grant.is_active(now),
        meter_ok=meter_ok,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Guard
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Reservation:
    """A live hold on one grant for one provider attempt."""

    guard: GrantGuard
    grant: ProviderGrant
    reservation_id: str
    worst_case_usd: float
    provider: str
    _done: bool = field(default=False, repr=False)

    async def settle(self, model: str | None, usage: dict[str, Any] | None) -> None:
        """Record actual spend. Missing usage ⇒ settle the worst case (never under-count)."""
        if self._done:
            return
        self._done = True
        actual: float | None = None
        if usage:
            actual = actual_cost_usd(self.provider, model, usage)
        if actual is None:
            actual = self.worst_case_usd
        await self.guard._settle(self, actual)

    async def settle_worst_case(self) -> None:
        if self._done:
            return
        self._done = True
        await self.guard._settle(self, self.worst_case_usd)

    async def release(self) -> None:
        if self._done:
            return
        self._done = True
        await self.guard._release(self)


@dataclass
class GuardDecision:
    allowed: bool
    reason: str
    reservation: Reservation | None = None
    grant_id: str | None = None


class GrantGuard:
    """Decides, per call, whether a provider may be used and holds its budget."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], GrantConfigState] | None = None,
        required: Iterable[str] | None = None,
        meter: GrantMeter | None = None,
        meter_factory: Callable[[], GrantMeter | None] | None = None,
        platform_orgs: Iterable[str] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        cache_seconds: float = CONFIG_RECHECK_SECONDS,
    ) -> None:
        self._loader = config_loader or load_grant_config
        self._required = frozenset(required) if required is not None else required_providers()
        self._meter = meter
        self._meter_factory = meter_factory
        # One meter per running event loop: an asyncio Redis client is bound
        # to the loop that created its connections, and workers run graph code
        # in more than one loop (``run_async`` helper threads). Sharing one
        # client across loops raised RuntimeError and failed the guard closed.
        self._loop_meters: dict[int, tuple[asyncio.AbstractEventLoop, GrantMeter | None]] = {}
        self._platform_orgs = (
            frozenset(platform_orgs) if platform_orgs is not None else platform_org_ids()
        )
        self._now = now_fn or (lambda: datetime.now(tz=UTC))
        self._cache_seconds = cache_seconds
        self._state: GrantConfigState | None = None
        self._state_loaded_at = 0.0
        self._last_error_log: dict[str, float] = {}
        self._background: set[asyncio.Task[None]] = set()
        self._logged_source: str | None = None

    # -- config ------------------------------------------------------------

    def state(self) -> GrantConfigState:
        mono = time.monotonic()
        if self._state is None or mono - self._state_loaded_at >= self._cache_seconds:
            self._state = self._loader()
            self._state_loaded_at = mono
            if self._state.error:
                self._log_error("config", "provider grants: INVALID config (%s) — guarded "
                                "providers are unavailable until it is fixed", self._state.error)
            elif self._logged_source != self._state.source + str(len(self._state.grants)):
                self._logged_source = self._state.source + str(len(self._state.grants))
                logger.info(
                    "provider grants: %d grant(s) loaded from %s (%s); required for: %s",
                    len(self._state.grants),
                    self._state.source,
                    ", ".join(g.id for g in self._state.grants) or "-",
                    ", ".join(sorted(self._required)) or "-",
                )
        return self._state

    @property
    def required(self) -> frozenset[str]:
        return self._required

    @property
    def enabled(self) -> bool:
        """False ⇒ nothing configured; the router skips the guard entirely."""
        st = self.state()
        return bool(self._required or st.grants)

    def is_guarded(self, provider_name: str) -> bool:
        st = self.state()
        return provider_name in self._required or any(
            g.provider == provider_name for g in st.grants
        )

    def grants(self) -> tuple[ProviderGrant, ...]:
        return self.state().grants

    # -- meter -------------------------------------------------------------

    def _build_meter(self) -> GrantMeter | None:
        assert self._meter_factory is not None
        try:
            return self._meter_factory()
        except Exception as exc:
            self._log_error("meter", "provider grants: cannot build the Redis meter: %s", exc)
            return None

    def meter(self) -> GrantMeter | None:
        if self._meter_factory is None:
            return self._meter
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            if self._meter is None:
                self._meter = self._build_meter()
            return self._meter
        entry = self._loop_meters.get(id(loop))
        if entry is not None and entry[0] is loop:
            return entry[1]
        for key, (other, _) in list(self._loop_meters.items()):
            if other.is_closed():
                del self._loop_meters[key]
        meter = self._build_meter()
        self._loop_meters[id(loop)] = (loop, meter)
        if self._meter is None:
            self._meter = meter
        return meter

    def all_meters(self) -> list[GrantMeter]:
        """Every meter this guard has built (for re-wiring, e.g. a new seeder)."""
        meters = [m for _, m in self._loop_meters.values() if m is not None]
        if self._meter is not None and all(self._meter is not m for m in meters):
            meters.append(self._meter)
        return meters

    # -- decisions ---------------------------------------------------------

    async def reserve(
        self,
        provider_name: str,
        org_id: str | None,
        model: str | None,
        request: InferenceRequest,
    ) -> GuardDecision:
        """Check org / window / ceiling and reserve the worst case for one attempt.

        Unguarded providers are always allowed with no reservation.
        """
        if not self.is_guarded(provider_name):
            return GuardDecision(True, "unguarded")
        st = self.state()
        required = provider_name in self._required
        if st.error:
            return GuardDecision(False, "config_invalid")
        now = self._now()
        candidates = [g for g in st.grants if g.provider == provider_name]
        if not candidates:
            return GuardDecision(False, "no_grant")
        if not org_id:
            return self._passthrough_or(required, "org_missing")
        for_org = [g for g in candidates if org_allowed(g, org_id, self._platform_orgs)]
        if not for_org:
            return self._passthrough_or(required, "org_not_allowed")
        active = sorted((g for g in for_org if g.is_active(now)), key=lambda g: g.expires_at)
        if not active:
            reason = "expired" if all(now >= g.expires_at for g in for_org) else "not_started"
            return self._passthrough_or(required, reason)
        worst = worst_case_cost_usd(provider_name, model, request)
        if worst is None:
            self._log_error("cost", "provider grants: madfam_budget_gate cost model is not "
                            "importable — guarded provider %s unavailable", provider_name)
            return GuardDecision(False, "cost_model_unavailable")
        meter = self.meter()
        if meter is None:
            self._log_error("meter", "provider grants: no Redis meter (set REDIS_URL) — guarded "
                            "provider %s unavailable", provider_name)
            return GuardDecision(False, "meter_unavailable")
        for grant in active:
            try:
                ok, rid = await meter.try_reserve(grant, worst, now)
            except Exception as exc:
                self._log_error("redis", "provider grants: Redis meter error (%s: %s) — guarded "
                                "provider %s unavailable", type(exc).__name__,
                                str(exc)[:200], provider_name)
                return GuardDecision(False, "meter_unavailable", grant_id=grant.id)
            if ok and rid is not None:
                return GuardDecision(
                    True,
                    "reserved",
                    Reservation(self, grant, rid, worst, provider_name),
                    grant.id,
                )
        logger.warning(
            "provider grants: ceiling reached for %s (grants: %s) — provider unavailable",
            provider_name,
            ", ".join(g.id for g in active),
        )
        return GuardDecision(False, "ceiling_reached", grant_id=active[0].id)

    def _passthrough_or(self, required: bool, reason: str) -> GuardDecision:
        # A provider that has grants but is NOT in PROVIDER_GRANTS_REQUIRED_FOR
        # may still be used outside them (e.g. a paid key); required ⇒ deny.
        if required:
            return GuardDecision(False, reason)
        return GuardDecision(True, f"unmetered:{reason}")

    async def _settle(self, res: Reservation, actual_usd: float) -> None:
        meter = self.meter()
        if meter is None:
            return
        try:
            await meter.settle(res.grant, res.reservation_id, actual_usd, self._now())
        except Exception as exc:
            self._log_error("settle", "provider grants: settle failed for grant %s (%s); the "
                            "reservation expires on its own", res.grant.id, type(exc).__name__)

    async def _release(self, res: Reservation) -> None:
        meter = self.meter()
        if meter is None:
            return
        try:
            await meter.release(res.grant, res.reservation_id)
        except Exception as exc:
            self._log_error("release", "provider grants: release failed for grant %s (%s); the "
                            "reservation expires on its own", res.grant.id, type(exc).__name__)

    def settle_in_background(self, res: Reservation) -> None:
        """Settle the worst case from a cancelled call without awaiting in the caller."""
        task = asyncio.ensure_future(res.settle_worst_case())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # -- status ------------------------------------------------------------

    async def statuses(self) -> list[GrantStatus]:
        st = self.state()
        now = self._now()
        meter = self.meter()
        out: list[GrantStatus] = []
        for grant in st.grants:
            snap: MeterSnapshot | None = None
            if meter is not None:
                try:
                    snap = await meter.snapshot(grant, now)
                except Exception as exc:
                    self._log_error("status", "provider grants: cannot read meter for %s (%s)",
                                    grant.id, type(exc).__name__)
            out.append(build_status(grant, snap, now))
        return out

    # -- logging -----------------------------------------------------------

    def _log_error(self, key: str, msg: str, *args: Any) -> None:
        mono = time.monotonic()
        if mono - self._last_error_log.get(key, -1e9) >= _ERROR_LOG_INTERVAL_SECONDS:
            self._last_error_log[key] = mono
            logger.error(msg, *args)


# ─────────────────────────────────────────────────────────────────────────────
# Process-wide default guard
# ─────────────────────────────────────────────────────────────────────────────

_default_guard: GrantGuard | None = None
_ledger_seeder: LedgerSeeder | None = None


def _redis_meter_from_env() -> GrantMeter | None:
    url = os.environ.get(ENV_REDIS_URL) or os.environ.get(ENV_FALLBACK_REDIS_URL)
    if not url:
        return None
    import redis.asyncio as aioredis  # same client convention as madfam_budget_gate

    client = aioredis.from_url(
        url, decode_responses=True, socket_connect_timeout=1.0, socket_timeout=2.0
    )
    try:
        ttl = int(os.environ.get(ENV_RESERVATION_TTL, DEFAULT_RESERVATION_TTL_SECONDS))
    except ValueError:
        ttl = DEFAULT_RESERVATION_TTL_SECONDS
    return GrantMeter(client, seeder=_ledger_seeder, reservation_ttl_seconds=ttl)


def get_default_guard() -> GrantGuard:
    """The process-wide guard, built from env on first use."""
    global _default_guard  # noqa: PLW0603
    if _default_guard is None:
        _default_guard = GrantGuard(meter_factory=_redis_meter_from_env)
    return _default_guard


def set_default_guard(guard: GrantGuard | None) -> None:
    """Replace (or with None, reset) the process-wide guard. For tests and wiring."""
    global _default_guard  # noqa: PLW0603
    _default_guard = guard


def set_ledger_seeder(seeder: LedgerSeeder | None) -> None:
    """Register how this process reads settled grant spend from the ledger.

    nexus-api and the inference gateway own the database and register one at
    startup; workers do not, and seed 0 (logged) on a cold Redis.
    """
    global _ledger_seeder  # noqa: PLW0603
    _ledger_seeder = seeder
    guard = _default_guard
    if guard is not None:
        for meter in guard.all_meters():
            meter.set_seeder(seeder)


async def get_grant_statuses() -> list[GrantStatus]:
    """Status of every declared grant (contract C2)."""
    return await get_default_guard().statuses()


def is_pinned_to(provider_name: str, model: str | None) -> bool:
    """True when ``model`` is a model id of ``provider_name`` (e.g. ``claude-*``)."""
    if not model:
        return False
    prefixes = PROVIDER_MODEL_PREFIXES.get(provider_name, ())
    return model.lower().startswith(prefixes) if prefixes else False
