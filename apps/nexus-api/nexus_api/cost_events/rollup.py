"""Classify ledger rows by who paid, roll them up per day, build ``cost.event.v1``.

Pure: no database, no network. ``runner`` feeds it ``LedgerRow`` tuples read from
``compute_token_ledger`` and gets back the events the outbox should hold plus
the counts of everything withheld.

Who paid (RFC 0050 ruling C13, finding F6)
==========================================
``cost_usd`` on a ledger row is a LIST-PRICE ESTIMATE from
``madfam_budget_gate.cost_model``, never an invoice. Each row with a provider is
one of:

* ``local`` — the provider runs on MADFAM's own compute (Ollama). Its cost is
  cluster compute (Waybill), not tokens. No event; the cost model even prices
  these rows at its high fallback rate, so their ``cost_usd`` is meaningless.
* ``grant`` — a declared provider credit grant covered the call: same provider,
  the call's time inside the grant window, the org allowed by the grant
  (exactly the grant guard's own test). Non-cash: a memo OUTSIDE COGS (C13).
  Sent only when Dhanam accepts the ``funding`` field (``funding_memo``), with
  ``cost_class: opex`` so it can never read as COGS.
* ``funding_unknown`` — the provider may only be used under a grant
  (``PROVIDER_GRANTS_REQUIRED_FOR``, or an extra account) yet no declared grant
  covers the row: the grants file is missing or was edited. Withheld, loudly:
  guessing "paid" would book a grant as cash.
* ``paid`` — everything else: MADFAM's own provider key, billed by the provider.

Every event is ``basis: estimate``: Dhanam stores it and never counts it, so
this emitter cannot double-count the provider's invoice that Dhanam already
holds as a payment. The events give the ledger the per-day, per-org,
per-product split; turning that split into counted COGS needs the allocation
contract change described in ``docs/COST_EVENTS.md``.

Cost class (RFC 0050 D3, C13)
=============================
Paid usage is ``cogs`` when it serves a client: an engagement is mapped for the
org, the calling service is a mapped client-facing product, or the org is a
Selva tenant other than MADFAM itself (Selva is the product). MADFAM's own
unattributed usage is shared platform overhead: ``opex`` until Waybill
allocation exists.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal, NamedTuple
from zoneinfo import ZoneInfo

from .config import FEATURE_FUNDING_MEMO, FEATURE_PRODUCT, CostEventsConfig

MEXICO_CITY = ZoneInfo("America/Mexico_City")
SCHEMA = "cost.event.v1"
SOURCE = "selva"
KIND = "inference"
BASIS = "estimate"
CURRENCY = "USD"
#: The product a non-platform tenant's usage serves when no caller mapping says otherwise.
SELVA_PRODUCT = "selva"

Funding = Literal["paid", "grant", "local", "funding_unknown"]

WITHHELD_LOCAL = "local_compute"
WITHHELD_GRANT_UNSUPPORTED = "grant_memo_unsupported"
WITHHELD_FUNDING_UNKNOWN = "funding_unknown"
WITHHELD_UNPRICED = "unpriced"
WITHHELD_BELOW_CENT = "below_one_cent"


class LedgerRow(NamedTuple):
    """The ``compute_token_ledger`` columns the rollup reads."""

    created_at: datetime
    org_id: str
    caller: str | None
    provider: str | None
    amount: int
    cost_usd: Decimal | None


class GrantWindow(NamedTuple):
    """The part of a ``madfam_inference.grants.ProviderGrant`` the classifier needs."""

    provider: str
    starts_at: datetime
    expires_at: datetime
    allowed_orgs: tuple[str, ...]


@dataclass(frozen=True)
class FundingRules:
    """What the grant guard knows, frozen for one run."""

    grants: tuple[GrantWindow, ...] = ()
    required_providers: frozenset[str] = frozenset()
    #: ``madfam_inference.grants.platform_org_ids()``: the ids the guard treats as one.
    guard_platform_orgs: frozenset[str] = frozenset({"madfam"})
    is_extra_credential: Callable[[str], bool] = lambda _provider: False


def _utc(at: datetime) -> datetime:
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def civil_day(at: datetime) -> date:
    """The civil date of an instant in America/Mexico_City (RFC 0050 period cut-off)."""
    return _utc(at).astimezone(MEXICO_CITY).date()


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """``[start, end)`` of a Mexico City civil day, in UTC."""
    start = datetime.combine(day, time.min, tzinfo=MEXICO_CITY)
    end = datetime.combine(date.fromordinal(day.toordinal() + 1), time.min, tzinfo=MEXICO_CITY)
    return start.astimezone(UTC), end.astimezone(UTC)


def _org_allowed(grant: GrantWindow, org_id: str, platform: frozenset[str]) -> bool:
    """Mirror of ``madfam_inference.grants.org_allowed`` (exact match + platform alias)."""
    if not org_id:
        return False
    if org_id in grant.allowed_orgs:
        return True
    ids = platform | {"madfam"}
    return org_id in ids and any(org in ids for org in grant.allowed_orgs)


def classify_funding(row: LedgerRow, rules: FundingRules, local: frozenset[str]) -> Funding:
    """Who paid for one ledger row with a provider (see the module docstring)."""
    provider = (row.provider or "").strip()
    if provider.lower() in local:
        return "local"
    at = _utc(row.created_at)
    for grant in rules.grants:
        if (
            grant.provider == provider
            and _utc(grant.starts_at) <= at < _utc(grant.expires_at)
            and _org_allowed(grant, row.org_id, rules.guard_platform_orgs)
        ):
            return "grant"
    if provider in rules.required_providers or rules.is_extra_credential(provider):
        return "funding_unknown"
    return "paid"


class GroupKey(NamedTuple):
    day: date
    org_id: str
    product: str | None
    engagement: str | None
    provider: str
    funding: str


@dataclass
class Totals:
    cost_usd: Decimal = Decimal(0)
    tokens: int = 0
    calls: int = 0
    unpriced_calls: int = 0
    unpriced_tokens: int = 0


@dataclass
class RollupResult:
    #: event id → payload, ready for the outbox.
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: event id → civil day, for the outbox's period column.
    days: dict[str, date] = field(default_factory=dict)
    rows_seen: int = 0
    rows_without_provider: int = 0
    #: reason → number of withheld (would-be) events.
    withheld_events: Counter[str] = field(default_factory=Counter)
    #: reason → withheld calls / tokens.
    withheld_calls: Counter[str] = field(default_factory=Counter)
    withheld_tokens: Counter[str] = field(default_factory=Counter)
    #: (funding, cost_class) → events built.
    built: Counter[tuple[str, str]] = field(default_factory=Counter)


def _client_ref(org_id: str) -> str:
    ref = f"selva-org:{org_id}"
    if len(ref) <= 128:
        return ref
    return "selva-org-sha256:" + hashlib.sha256(org_id.encode()).hexdigest()[:40]


def cost_class_for(key: GroupKey, platform_orgs: frozenset[str]) -> str:
    if key.funding == "grant":
        return "opex"  # C13: a non-cash memo is never COGS
    if key.engagement or key.product or key.org_id not in platform_orgs:
        return "cogs"
    return "opex"  # shared platform overhead stays OpEx until Waybill allocation (C13)


def event_id(key: GroupKey) -> str:
    """Deterministic ``(source, id)`` idempotency key: same group, same id, forever."""
    digest = hashlib.sha256(
        "\0".join(
            [key.org_id, key.product or "", key.engagement or "", key.provider, key.funding]
        ).encode()
    ).hexdigest()[:24]
    return f"selva:inference:{key.day:%Y%m%d}:{digest}"


def occurred_at(day: date) -> str:
    """The last second of the civil day, with its Mexico City offset."""
    return datetime.combine(day, time(23, 59, 59), tzinfo=MEXICO_CITY).isoformat()


def to_minor(cost_usd: Decimal) -> int:
    return int((cost_usd * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def build_event(
    key: GroupKey, totals: Totals, cfg: CostEventsConfig, amount_minor: int
) -> dict[str, Any]:
    attribution: dict[str, str] = {"client_ref": _client_ref(key.org_id)}
    if key.engagement:
        attribution["engagement"] = f"eng:{key.engagement}"
    if key.product and cfg.has(FEATURE_PRODUCT):
        attribution["product"] = key.product
    event: dict[str, Any] = {
        "schema": SCHEMA,
        "id": event_id(key),
        "source": SOURCE,
        "kind": KIND,
        "occurred_at": occurred_at(key.day),
        "amount_minor": amount_minor,
        "currency": CURRENCY,
        "cost_class": cost_class_for(key, cfg.platform_orgs),
        "basis": BASIS,
        "quantity": str(totals.tokens),
        "unit": "token",
        "item": {
            "description": (
                f"LLM inference via {key.provider[:40]}: "
                f"{totals.calls - totals.unpriced_calls} calls, "
                "list-price estimate"
            )
        },
        "attribution": attribution,
    }
    if key.funding == "grant":
        event["funding"] = "grant"
    return event


def rollup(
    rows: Iterable[LedgerRow],
    cfg: CostEventsConfig,
    rules: FundingRules,
    days: frozenset[date],
) -> RollupResult:
    """Group the rows of ``days`` and build the events the outbox should hold."""
    result = RollupResult()
    groups: dict[GroupKey, Totals] = {}
    for row in rows:
        result.rows_seen += 1
        day = civil_day(row.created_at)
        if day not in days:
            continue
        if not (row.provider or "").strip():
            result.rows_without_provider += 1  # budget debits (dispatch), not inference
            continue
        funding = classify_funding(row, rules, cfg.local_providers)
        org = row.org_id or "platform"
        product = cfg.product_by_caller.get(row.caller or "")
        if product is None and org not in cfg.platform_orgs:
            product = SELVA_PRODUCT
        key = GroupKey(
            day=day,
            org_id=org,
            product=product,
            engagement=cfg.engagement_by_org.get(org),
            provider=(row.provider or "").strip(),
            funding=funding,
        )
        totals = groups.setdefault(key, Totals())
        tokens = max(0, int(row.amount or 0))
        totals.calls += 1
        if row.cost_usd is None:
            totals.unpriced_calls += 1
            totals.unpriced_tokens += tokens
        else:
            totals.tokens += tokens
            totals.cost_usd += Decimal(row.cost_usd)

    for key, totals in sorted(groups.items(), key=_sort_key):
        reason = _withheld_reason(key, totals, cfg)
        if reason:
            result.withheld_events[reason] += 1
            result.withheld_calls[reason] += totals.calls
            result.withheld_tokens[reason] += totals.tokens + totals.unpriced_tokens
            continue
        if totals.unpriced_calls:
            # Priced calls still go out; the unpriced ones are counted, never guessed.
            result.withheld_calls[WITHHELD_UNPRICED] += totals.unpriced_calls
            result.withheld_tokens[WITHHELD_UNPRICED] += totals.unpriced_tokens
        amount = to_minor(totals.cost_usd)
        event = build_event(key, totals, cfg, amount)
        result.events[event["id"]] = event
        result.days[event["id"]] = key.day
        result.built[(key.funding, event["cost_class"])] += 1
    return result


def _sort_key(item: tuple[GroupKey, Totals]) -> tuple[str, ...]:
    """Stable order; ``None`` product / engagement sort as empty (never compared to str)."""
    return tuple("" if part is None else str(part) for part in item[0])


def _withheld_reason(key: GroupKey, totals: Totals, cfg: CostEventsConfig) -> str | None:
    if key.funding == "local":
        return WITHHELD_LOCAL
    if key.funding == "funding_unknown":
        return WITHHELD_FUNDING_UNKNOWN
    if key.funding == "grant" and not cfg.has(FEATURE_FUNDING_MEMO):
        return WITHHELD_GRANT_UNSUPPORTED
    if totals.calls == totals.unpriced_calls:
        return WITHHELD_UNPRICED
    if to_minor(totals.cost_usd) == 0:
        return WITHHELD_BELOW_CENT
    return None
