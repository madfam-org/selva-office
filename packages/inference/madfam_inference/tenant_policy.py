"""Per-tenant inference policy — sensitivity floor, caps, and rate limits.

The gateway's org-config (``org-config.yaml``) is *ecosystem-wide*: it
says which provider serves which task type. This module adds the missing
*per-tenant* layer: what a given ``X-Selva-Tenant-Org`` is allowed and
budgeted to do.

Why it exists
-------------
Before this, a tenant handling regulated personal data depended entirely
on its own client code sending ``X-Sensitivity: restricted`` on every call. A dropped header, a
proxy that strips it, or a new surface that forgets it, and the request
silently degraded to ``public`` and went to a cloud vendor. The header is
now mandatory (the proxy rejects a request without it), and on top of that
a tenant can declare a **sensitivity floor**: the level its data can never
fall below, enforced server-side regardless of what the client sends.

Design notes
------------
- **Declarative, not code.** Policies load from YAML (``TENANT_POLICY_PATH``,
  shipped as a ConfigMap) so onboarding a regulated tenant is a config
  change reviewed in Git, not a deploy of new logic.
- **Absent policy = no extra restriction.** A tenant with no entry keeps
  today's behaviour exactly. This module only ever *tightens*.
- **The floor raises, never lowers.** A tenant with floor ``restricted``
  that sends ``public`` is served as ``restricted``. A tenant with floor
  ``internal`` that sends ``restricted`` is served as ``restricted`` —
  the caller may always ask for MORE protection than its floor.
- **Rate limiting is in-process** (per pod, fixed window). It is a blunt
  abuse/runaway brake, not a billing meter; the durable USD attribution is
  the ``inference_usage_ledger``. With N replicas the effective limit is
  N × the configured value — state that when you set the number.

Task exceptions
---------------
The one deliberate way below a floor is a :class:`TaskException`: an
owner-authorized, per-task exception for pseudonymized payloads. It is as
narrow as the code can make it — one tenant, one task type, a request that
declares ``internal`` and attests ``X-Pseudonymized: true``, a named list of
providers intersected with the router's ``internal`` set, and models pinned
per provider. Anything short of all of that gets the floor, and a malformed
exception is dropped at load (logged at ERROR) while the tenant and its
floor still load: an exception fails CLOSED, never the floor.

No prompt or completion text ever reaches this module.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .router import CLOUD_PRIORITY
from .types import Sensitivity

logger = logging.getLogger(__name__)

#: The one attestation a task exception accepts: the client's statement that
#: it pseudonymized the payload (stripped every name) before sending it.
#: Fixed in code on purpose. A free-form header in config could be mistyped,
#: or set to a header every client already sends, and the "attestation" would
#: then attest nothing.
PSEUDONYMIZATION_HEADER = "X-Pseudonymized"
PSEUDONYMIZATION_ATTESTED_VALUE = "true"
PSEUDONYMIZATION_REQUIREMENT = f"{PSEUDONYMIZATION_HEADER}: {PSEUDONYMIZATION_ATTESTED_VALUE}"

DEFAULT_TENANT_POLICY_PATH = "/etc/selva/tenant-policies.yaml"
ENV_TENANT_POLICY_PATH = "TENANT_POLICY_PATH"

# Ordered weakest → strongest. ``max()`` over this order is how the floor
# is applied, so a caller asking for MORE protection than its floor keeps
# the stronger level.
_SENSITIVITY_ORDER: dict[Sensitivity, int] = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.INTERNAL: 1,
    Sensitivity.CONFIDENTIAL: 2,
    Sensitivity.RESTRICTED: 3,
}


def sensitivity_rank(level: Sensitivity) -> int:
    """Return the ordinal strength of a sensitivity level (higher = stricter)."""
    return _SENSITIVITY_ORDER[level]


def apply_floor(requested: Sensitivity, floor: Sensitivity | None) -> Sensitivity:
    """Return the stricter of ``requested`` and ``floor``.

    ``floor`` of ``None`` (no tenant policy) returns ``requested`` unchanged.
    """
    if floor is None:
        return requested
    return requested if sensitivity_rank(requested) >= sensitivity_rank(floor) else floor


class TaskException(BaseModel):
    """One owner-authorized exception to a tenant's floor, for ONE task type.

    It applies to a request only when ALL of these hold — otherwise the
    tenant floor applies exactly as if the exception did not exist:

    - the request's tenant declares this exception (keyed by task type);
    - ``X-Task-Type`` is that task type;
    - the request DECLARES ``X-Sensitivity`` equal to ``sensitivity_floor``
      (only ``internal`` is accepted) — not lower, not higher;
    - it carries ``X-Pseudonymized: true``.

    Inside it, the request may be served only by ``allowed_providers`` (in
    order: primary first, then the fallback chain) intersected with the
    router's ``internal`` set, each with the model pinned in ``models``.
    Every other tenant limit — task-type allowlist, output cap, deadline,
    rate limit, budget, no persistence — still applies.

    Validation is strict, and any failure drops the exception (ERROR) but
    never the tenant, so a broken exception fails closed to the floor.
    """

    model_config = ConfigDict(extra="forbid")

    #: The level the request must declare, and is served at. ``internal`` only.
    sensitivity_floor: Sensitivity
    #: Ordered: the first registered provider serves, the rest are the
    #: fallback chain. Each must be in the router's ``internal`` set.
    allowed_providers: list[str]
    #: Must be exactly ``"X-Pseudonymized: true"``. Spelled out in the config
    #: so the condition is visible where the exception is declared.
    requires_header: str
    #: Provider -> model id, exactly one per allowed provider.
    models: dict[str, str]
    #: Date of the owner's decision; carried into the startup log.
    authorized_on: date
    #: Free text for operators. Never sent to a provider.
    notes: str = ""

    @field_validator("sensitivity_floor")
    @classmethod
    def _internal_only(cls, value: Sensitivity) -> Sensitivity:
        if value is not Sensitivity.INTERNAL:
            raise ValueError(f"a task exception may only serve at 'internal', not {value.value!r}")
        return value

    @field_validator("allowed_providers")
    @classmethod
    def _internal_set_providers_only(cls, value: list[str]) -> list[str]:
        names = [name.strip() for name in value]
        if not names or any(not name for name in names):
            raise ValueError("allowed_providers must name at least one provider, none blank")
        if len(set(names)) != len(names):
            raise ValueError("allowed_providers names a provider twice")
        outside = [name for name in names if name not in CLOUD_PRIORITY]
        if outside:
            raise ValueError(f"allowed_providers {outside} are not in the router's internal set")
        return names

    @field_validator("requires_header")
    @classmethod
    def _the_attestation(cls, value: str) -> str:
        name, separator, header_value = value.partition(":")
        if (
            not separator
            or name.strip().lower() != PSEUDONYMIZATION_HEADER.lower()
            or header_value.strip().lower() != PSEUDONYMIZATION_ATTESTED_VALUE
        ):
            raise ValueError(f"requires_header must be {PSEUDONYMIZATION_REQUIREMENT!r}")
        return PSEUDONYMIZATION_REQUIREMENT

    @field_validator("models")
    @classmethod
    def _no_blank_model(cls, value: dict[str, str]) -> dict[str, str]:
        models = {provider.strip(): model.strip() for provider, model in value.items()}
        if any(not model for model in models.values()):
            raise ValueError("models has a provider with a blank model id")
        return models

    @model_validator(mode="after")
    def _one_model_per_provider(self) -> TaskException:
        missing = [name for name in self.allowed_providers if name not in self.models]
        if missing:
            raise ValueError(f"models must pin a model per allowed provider; missing {missing}")
        stray = sorted(set(self.models) - set(self.allowed_providers))
        if stray:
            raise ValueError(f"models names provider(s) outside allowed_providers: {stray}")
        return self


class TenantPolicy(BaseModel):
    """Server-side policy for one ``X-Selva-Tenant-Org``.

    Every field is optional; an omitted field means "no tenant-specific
    restriction, use the gateway default".
    """

    org_id: str
    #: Human name, for operator logs and the runbook. Never sent to a provider.
    display_name: str = ""
    #: The weakest sensitivity this tenant's data may ever be served at.
    #: A request that asks for less is RAISED to this level, not rejected.
    sensitivity_floor: Sensitivity | None = None
    #: Task types this tenant is allowed to send. Empty = all allowed.
    #: A denied task type is a 400, not a silent downgrade.
    allowed_task_types: list[str] = Field(default_factory=list)
    #: Hard ceiling on ``max_tokens`` for this tenant's requests.
    max_tokens_cap: int | None = None
    #: Server-side deadline for one completion, in seconds.
    request_timeout_seconds: float | None = None
    #: In-process fixed-window request cap. ``None`` = unlimited.
    rate_limit_per_minute: int | None = None
    #: Informational daily USD budget. Recorded for attribution and surfaced
    #: to operators; enforcement lives in the budget gate when it is armed.
    daily_usd_budget: float | None = None
    #: Free-text note carried into operator logs (contract reference, owner).
    notes: str = ""
    #: Owner-authorized exceptions to ``sensitivity_floor``, keyed by task
    #: type. See :class:`TaskException`. Empty = none: the floor applies to
    #: every task. The loader validates each entry on its own and drops (with
    #: an ERROR) any that fails, so a bad entry can only ever leave the floor
    #: in force.
    task_exceptions: dict[str, TaskException] = Field(default_factory=dict)


def pseudonymization_attested(value: str | None) -> bool:
    """True only when ``X-Pseudonymized`` carries the accepted attestation."""
    return (value or "").strip().lower() == PSEUDONYMIZATION_ATTESTED_VALUE


def pseudonymization_header_sent(value: str | None) -> bool:
    """True when ``X-Pseudonymized`` was sent at all, whatever its value.

    The gateway uses this to fail closed: a request that says it is on the
    pseudonymized path but matches no valid exception is served as
    ``restricted`` — even for a tenant with no policy loaded — instead of
    being routed as the ``internal`` it declared.
    """
    return bool((value or "").strip())


def resolve_task_exception(
    policy: TenantPolicy | None,
    *,
    task_type: str | None,
    declared: Sensitivity,
    pseudonymized: str | None,
) -> TaskException | None:
    """Return the task exception that applies to this request, or ``None``.

    ``None`` means "apply the tenant floor exactly as without exceptions".
    Every condition is required; there is no partial match:

    - ``policy`` (the request's tenant) declares an exception for ``task_type``;
    - ``declared`` is exactly the exception's level (``internal``), so an
      under-declared ``public`` and an over-declared ``restricted`` or
      ``confidential`` both keep the floor;
    - ``pseudonymized`` is the ``X-Pseudonymized: true`` attestation.
    """
    if policy is None or not task_type:
        return None
    exception = policy.task_exceptions.get(task_type)
    if exception is None:
        return None
    if declared is not exception.sensitivity_floor:
        return None
    if not pseudonymization_attested(pseudonymized):
        return None
    return exception


class TenantPolicyBook(BaseModel):
    """The full set of tenant policies plus gateway-wide defaults."""

    #: Applied to every tenant that has no explicit policy of its own.
    default_request_timeout_seconds: float = 45.0
    default_max_tokens_cap: int = 4096
    tenants: dict[str, TenantPolicy] = Field(default_factory=dict)

    def for_org(self, org_id: str | None) -> TenantPolicy | None:
        """Return the policy for ``org_id``, or ``None`` when unconfigured."""
        if not org_id:
            return None
        return self.tenants.get(org_id)

    def timeout_for(self, policy: TenantPolicy | None) -> float:
        """Resolve the effective request timeout for a (possibly absent) policy."""
        if policy is not None and policy.request_timeout_seconds is not None:
            return policy.request_timeout_seconds
        return self.default_request_timeout_seconds

    def max_tokens_for(self, policy: TenantPolicy | None) -> int:
        """Resolve the effective ``max_tokens`` ceiling."""
        if policy is not None and policy.max_tokens_cap is not None:
            return policy.max_tokens_cap
        return self.default_max_tokens_cap


def _validation_reason(exc: ValidationError) -> str:
    """Summarise a validation failure as ``field: message`` pairs."""
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'entry'}: {error['msg']}"
        for error in exc.errors()
    )


def _parse_task_exceptions(
    org_id: str, raw: Any, allowed_task_types: list[str]
) -> dict[str, TaskException]:
    """Validate a tenant's ``task_exceptions`` block one entry at a time.

    Fails CLOSED per entry and LOUDLY: a block that is not a mapping, or an
    entry that does not validate, is dropped with an ERROR naming the tenant
    and the task, and the floor keeps applying to that task. An entry for a
    task type outside the tenant's ``allowed_task_types`` is dropped the same
    way — it could never apply, and a silent no-op exception is a config bug
    an operator should hear about.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        logger.error(
            "tenant policy: task_exceptions for %s must be a mapping of task type to "
            "exception; NONE is in force and the tenant floor applies to every task",
            org_id,
        )
        return {}

    exceptions: dict[str, TaskException] = {}
    for key, body in raw.items():
        task_type = str(key)
        if allowed_task_types and task_type not in allowed_task_types:
            reason = "the task type is not in this tenant's allowed_task_types"
        else:
            try:
                exceptions[task_type] = TaskException.model_validate(body)
                continue
            except ValidationError as exc:
                reason = _validation_reason(exc)
            except Exception as exc:  # any failure at all must fail closed
                reason = type(exc).__name__
        logger.error(
            "tenant policy: task exception %r for %s is INVALID and NOT in force; the "
            "tenant floor applies to that task. Reason: %s",
            task_type,
            org_id,
            reason,
        )
    return exceptions


def _parse_book(raw: dict[str, Any]) -> TenantPolicyBook:
    """Build a :class:`TenantPolicyBook` from a raw YAML mapping.

    Tenants may be given either as a mapping keyed by org id or as a list
    of objects each carrying ``org_id`` — both shapes read naturally in a
    ConfigMap, so both are accepted.
    """
    tenants_raw = raw.get("tenants") or {}
    tenants: dict[str, TenantPolicy] = {}

    if isinstance(tenants_raw, dict):
        items = [
            {**(value or {}), "org_id": (value or {}).get("org_id", key)}
            for key, value in tenants_raw.items()
        ]
    elif isinstance(tenants_raw, list):
        items = [item for item in tenants_raw if isinstance(item, dict)]
    else:
        logger.warning("tenant policy: 'tenants' must be a mapping or a list; ignoring")
        items = []

    for item in items:
        # Task exceptions are validated apart from the tenant: a malformed
        # exception must drop only itself, never the tenant and its floor.
        fields = dict(item)
        raw_exceptions = fields.pop("task_exceptions", None)
        try:
            policy = TenantPolicy(**fields)
        except Exception:
            logger.warning(
                "tenant policy: skipping malformed entry for %s",
                fields.get("org_id", "<unknown>"),
                exc_info=True,
            )
            continue
        policy.task_exceptions = _parse_task_exceptions(
            policy.org_id, raw_exceptions, policy.allowed_task_types
        )
        tenants[policy.org_id] = policy

    book_kwargs: dict[str, Any] = {"tenants": tenants}
    for key in ("default_request_timeout_seconds", "default_max_tokens_cap"):
        if key in raw and raw[key] is not None:
            book_kwargs[key] = raw[key]
    return TenantPolicyBook(**book_kwargs)


@lru_cache(maxsize=1)
def load_tenant_policies(path: Path | None = None) -> TenantPolicyBook:
    """Load the tenant policy book from YAML, cached per process.

    A missing file is normal (most deployments have no regulated tenant)
    and yields an empty book with gateway defaults. A malformed file is a
    LOUD warning and also yields the empty book — it must never silently
    remove a floor that an operator believes is in force, so the runbook
    tells operators to verify the loaded tenant list at startup.
    """
    config_path = path or Path(
        os.environ.get(ENV_TENANT_POLICY_PATH, DEFAULT_TENANT_POLICY_PATH)
    ).expanduser()

    if not config_path.exists():
        logger.info(
            "tenant policy: no policy file at %s — no per-tenant floors in force",
            config_path,
        )
        return TenantPolicyBook()

    try:
        import yaml

        raw = yaml.safe_load(config_path.read_text()) or {}
        book = _parse_book(raw)
        logger.info(
            "tenant policy: loaded %d tenant(s) from %s: %s",
            len(book.tenants),
            config_path,
            ", ".join(sorted(book.tenants)) or "(none)",
        )
        # One line per exception in force, so an operator can confirm at
        # startup exactly which exceptions exist — and that a removed one is
        # really gone.
        for org_id, policy in sorted(book.tenants.items()):
            for task_type, exception in sorted(policy.task_exceptions.items()):
                logger.info(
                    "tenant policy: %s task exception in force: task_type=%s served at %s "
                    "via %s only, requires %r, authorized %s",
                    org_id,
                    task_type,
                    exception.sensitivity_floor.value,
                    ", ".join(exception.allowed_providers),
                    PSEUDONYMIZATION_REQUIREMENT,
                    exception.authorized_on.isoformat(),
                )
        return book
    except ImportError:
        logger.warning("tenant policy: PyYAML not installed — no per-tenant floors in force")
        return TenantPolicyBook()
    except Exception:
        logger.error(
            "tenant policy: FAILED to parse %s — no per-tenant floors in force. "
            "Fix the file and restart; do not assume a floor is applied.",
            config_path,
            exc_info=True,
        )
        return TenantPolicyBook()


class InProcessRateLimiter:
    """Fixed-window per-key request limiter, in memory.

    Deliberately dependency-free: the inference gateway does not run Redis
    (see ``apps/inference-gateway/inference_gateway/main.py``), and adding
    one to enforce a tenant brake would put the LLM chokepoint's uptime
    behind a cache. With N replicas the effective ceiling is N × ``limit``;
    set the number knowing that, and treat it as a runaway brake rather
    than a billing meter.
    """

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int | None) -> tuple[bool, int]:
        """Record a hit for ``key``; return ``(allowed, retry_after_seconds)``.

        ``limit`` of ``None`` or a non-positive value means unlimited: the
        hit is not even recorded, so an unlimited tenant costs nothing.
        """
        if limit is None or limit <= 0:
            return True, 0

        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(self._window - (now - bucket[0])) + 1)
                return False, retry_after
            bucket.append(now)
            return True, 0

    def reset(self) -> None:
        """Drop all counters — used by tests."""
        with self._lock:
            self._hits.clear()
