"""Pure selection + pacing logic for the credit-investment autopilot.

No I/O here: the loop in ``credit_autopilot.py`` feeds grant status (lane
LG's ``madfam_inference.grants.get_grant_statuses()``, contract C2), the
backlog (``data/credit-investment/backlog.yaml``) and the current per-item
task states, and gets back which items to start and on which model tier.

Rules (see docs/CREDIT_AUTOPILOT.md):

* Spend only while the grant is alive and ``pace_status`` is ``behind`` or
  ``on_pace``; never when ``ahead``, ``exhausted`` or ``expired``, when the
  remaining budget is at or below the floor, or too close to expiry.
* Bounded concurrency: never more than ``max_concurrency`` items in flight.
* Tier per item, within the item's allowed tiers only: start at the
  preferred tier; upgrade to the most capable allowed tier when far behind
  pace; downgrade when the remaining budget cannot cover the item, when the
  grant is nearly used, or when time is short; skip the item when no allowed
  tier fits.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .credit_autopilot_steps import Target, targets_for

#: Model id per tier (current Anthropic ids).
TIER_MODELS: dict[str, str] = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}
#: Cheapest first.
TIER_ORDER: tuple[str, ...] = ("haiku", "sonnet", "opus")
#: Relative cost per tier (output-price ratio from the cost model, opus = 1).
TIER_COST_FACTOR: dict[str, float] = {"opus": 1.0, "sonnet": 0.5, "haiku": 0.025}

SPENDING_PACE = frozenset({"behind", "on_pace"})
IN_FLIGHT_STATUSES = frozenset({"pending", "queued", "running"})
DONE_STATUSES = frozenset({"completed"})
#: Graphs the autopilot may dispatch: read-only (LLM + search) only.
SAFE_DISPATCH_GRAPHS = frozenset({"research"})
SUPPORTED_MODES = frozenset({"generate", "dispatch", "benchmark"})


@dataclass(frozen=True)
class BacklogItem:
    id: str
    rank: int
    line: str
    mode: str
    tiers: tuple[str, ...]
    budget_share: float
    objective: str = ""
    deliverable: str = ""
    graph: str | None = None
    max_output_tokens: int = 8000
    context: tuple[tuple[str, str], ...] = ()
    allowed_tools: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    #: Multi-step fields (see credit_autopilot_steps).
    fanout: tuple[Target, ...] = ()
    refine_rounds: int = 0
    depends_on: tuple[str, ...] = ()
    output: str = "markdown"
    json_min_items: int = 0
    parallel: int = 2
    benchmark: tuple[tuple[str, Any], ...] = ()

    def targets(self) -> list[Target]:
        return list(self.fanout) or [Target(id=self.id)]


@dataclass(frozen=True)
class GrantView:
    id: str
    provider: str
    ceiling_usd: float
    remaining_usd: float
    seconds_to_expiry: float
    pace_status: str
    burn_usd_per_hour_60m: float
    required_usd_per_hour: float
    autopilot: bool


@dataclass(frozen=True)
class ItemState:
    item_id: str
    status: str
    attempts: int = 1


@dataclass(frozen=True)
class AutopilotConfig:
    floor_usd: float = 2.0
    max_concurrency: int = 6
    max_attempts: int = 2
    min_seconds_to_expiry: float = 900.0
    short_time_seconds: float = 3600.0
    low_remaining_fraction: float = 0.15
    far_behind_ratio: float = 2.0
    #: Keep starting work while ``ahead`` of pace. For an expiring grant whose
    #: value backlog exceeds the ceiling, idling to "spread" spend only risks
    #: leaving credit unused at expiry; the ceiling, floor and expiry cut-off
    #: still stop new work. Off by default (paced behaviour unchanged).
    front_load: bool = False


@dataclass(frozen=True)
class Selection:
    item: BacklogItem
    tier: str
    model: str
    reason: str


@dataclass
class Decision:
    run: bool
    reason: str
    selections: list[Selection] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)


class BacklogError(ValueError):
    """The backlog file is invalid."""


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def coerce_grant(obj: Any) -> GrantView | None:
    """Build a ``GrantView`` from a C2 ``GrantStatus`` (object or mapping)."""
    try:
        return GrantView(
            id=str(_get(obj, "id")),
            provider=str(_get(obj, "provider", "")),
            ceiling_usd=float(_get(obj, "ceiling_usd", 0.0) or 0.0),
            remaining_usd=float(_get(obj, "remaining_usd", 0.0) or 0.0),
            seconds_to_expiry=float(_get(obj, "seconds_to_expiry", 0.0) or 0.0),
            pace_status=str(_get(obj, "pace_status", "")),
            burn_usd_per_hour_60m=float(_get(obj, "burn_usd_per_hour_60m", 0.0) or 0.0),
            required_usd_per_hour=float(_get(obj, "required_usd_per_hour", 0.0) or 0.0),
            autopilot=bool(_get(obj, "autopilot", False)),
        )
    except (TypeError, ValueError):
        return None


def choose_grant(grants: Iterable[Any], provider: str = "anthropic") -> GrantView | None:
    """Pick the autopilot grant to invest: alive, opted in, soonest expiry."""
    candidates = []
    for raw in grants:
        grant = coerce_grant(raw)
        if grant is None or not grant.autopilot or grant.provider != provider:
            continue
        if grant.pace_status in {"exhausted", "expired"} or grant.seconds_to_expiry <= 0:
            continue
        candidates.append(grant)
    if not candidates:
        return None
    return min(candidates, key=lambda g: g.seconds_to_expiry)


def stop_reason(grant: GrantView, cfg: AutopilotConfig) -> str | None:
    """Return why the autopilot must not start new work, or None."""
    if grant.pace_status in {"exhausted", "expired"}:
        return f"grant {grant.pace_status}"
    if grant.seconds_to_expiry <= cfg.min_seconds_to_expiry:
        return "too close to expiry"
    if grant.remaining_usd <= cfg.floor_usd:
        return "remaining at or below floor"
    if grant.pace_status == "ahead" and cfg.front_load:
        return None
    if grant.pace_status not in SPENDING_PACE:
        return f"pace {grant.pace_status or 'unknown'}: no new work"
    return None


def _by_cost(tiers: Iterable[str]) -> list[str]:
    return sorted(set(tiers), key=TIER_ORDER.index)


def choose_tier(
    item: BacklogItem, grant: GrantView, cfg: AutopilotConfig
) -> tuple[str, str] | None:
    """Return ``(tier, reason)`` for the item, or None to skip it."""
    allowed = _by_cost(t for t in item.tiers if t in TIER_MODELS)
    if not allowed:
        return None
    preferred = item.tiers[0] if item.tiers[0] in TIER_MODELS else allowed[-1]
    tier = preferred
    reasons = [f"preferred {preferred}"]

    time_short = grant.seconds_to_expiry < cfg.short_time_seconds
    far_behind = (
        grant.pace_status == "behind"
        and not time_short
        and grant.required_usd_per_hour
        > cfg.far_behind_ratio * max(grant.burn_usd_per_hour_60m, 0.01)
    )
    if far_behind and allowed[-1] != tier:
        tier = allowed[-1]
        reasons.append(f"far behind pace -> {tier}")

    def step_down(current: str) -> str | None:
        idx = allowed.index(current)
        return allowed[idx - 1] if idx > 0 else None

    low_fraction = grant.ceiling_usd > 0 and (
        grant.remaining_usd / grant.ceiling_usd < cfg.low_remaining_fraction
    )
    if time_short or low_fraction:
        cheaper = step_down(tier)
        if cheaper is not None:
            tier = cheaper
            reasons.append(("time short" if time_short else "grant nearly used") + f" -> {tier}")

    spendable = grant.remaining_usd - cfg.floor_usd
    item_budget = item.budget_share * grant.ceiling_usd

    def est(t: str) -> float:
        return item_budget * TIER_COST_FACTOR[t] / TIER_COST_FACTOR[preferred]

    while est(tier) > spendable:
        cheaper = step_down(tier)
        if cheaper is None:
            return None
        tier = cheaper
        reasons.append(f"remaining cannot cover item -> {tier}")
    return tier, "; ".join(reasons)


def plan_dispatch(
    grant: GrantView,
    items: Sequence[BacklogItem],
    states: Mapping[str, ItemState],
    cfg: AutopilotConfig,
) -> Decision:
    """Decide which backlog items to start this tick."""
    reason = stop_reason(grant, cfg)
    if reason is not None:
        return Decision(run=False, reason=reason)

    in_flight = sum(1 for s in states.values() if s.status in IN_FLIGHT_STATUSES)
    slots = cfg.max_concurrency - in_flight
    if slots <= 0:
        return Decision(run=True, reason=f"{in_flight} item(s) in flight; no free slot")

    decision = Decision(run=True, reason="dispatching")
    time_short = grant.seconds_to_expiry < cfg.short_time_seconds
    for item in sorted(items, key=lambda i: (i.rank, i.id)):
        if len(decision.selections) >= slots:
            break
        state = states.get(item.id)
        if state is not None:
            if state.status in IN_FLIGHT_STATUSES or state.status in DONE_STATUSES:
                continue
            if state.attempts >= cfg.max_attempts:
                decision.skipped[item.id] = "max attempts reached"
                continue
        unmet = [
            d for d in item.depends_on if (states.get(d) is None or states[d].status != "completed")
        ]
        if unmet:
            decision.skipped[item.id] = f"waiting on {', '.join(unmet)}"
            continue
        if item.mode not in SUPPORTED_MODES:
            decision.skipped[item.id] = f"unsupported mode {item.mode}"
            continue
        if item.mode == "dispatch":
            if item.graph not in SAFE_DISPATCH_GRAPHS:
                decision.skipped[item.id] = f"graph {item.graph} not allowed for autopilot"
                continue
            if time_short:
                decision.skipped[item.id] = "time short for a graph run"
                continue
        choice = choose_tier(item, grant, cfg)
        if choice is None:
            decision.skipped[item.id] = "no allowed tier fits the remaining budget"
            continue
        tier, why = choice
        decision.selections.append(
            Selection(item=item, tier=tier, model=TIER_MODELS[tier], reason=why)
        )
    if not decision.selections:
        decision.reason = "nothing eligible"
    return decision


def parse_backlog(data: Any) -> list[BacklogItem]:
    """Validate the backlog document and return its items.

    Raises ``BacklogError`` on schema problems, on a forbidden tool in any
    item's ``allowed_tools``, on an amount-like key (the file is public),
    or when the budget shares add up to more than the whole grant.
    """
    if not isinstance(data, Mapping) or data.get("schema") != "selva.credit-investment-backlog/v1":
        raise BacklogError("expected schema selva.credit-investment-backlog/v1")
    forbidden = {str(t) for t in data.get("forbidden_tools") or []}
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise BacklogError("'items' must be a non-empty list")

    items: list[BacklogItem] = []
    seen: set[str] = set()
    total_share = 0.0
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise BacklogError("each item must be a mapping")
        item_id = str(raw.get("id") or "")
        if not item_id or item_id in seen:
            raise BacklogError(f"missing or duplicate item id {item_id!r}")
        seen.add(item_id)
        for key in raw:
            if any(word in str(key) for word in ("amount", "usd", "price", "expires")):
                raise BacklogError(f"{item_id}: key {key!r} not allowed in a public backlog")
        tiers = tuple(str(t) for t in raw.get("tiers") or [])
        if not tiers or any(t not in TIER_MODELS for t in tiers):
            raise BacklogError(
                f"{item_id}: tiers must be a non-empty subset of {list(TIER_MODELS)}"
            )
        tools = tuple(str(t) for t in raw.get("allowed_tools") or [])
        bad = forbidden.intersection(tools)
        if bad:
            raise BacklogError(f"{item_id}: forbidden tool(s) {sorted(bad)}")
        share = float(raw.get("budget_share") or 0.0)
        if not 0.0 < share <= 1.0:
            raise BacklogError(f"{item_id}: budget_share must be in (0, 1]")
        total_share += share
        mode = str(raw.get("mode") or "")
        if mode not in SUPPORTED_MODES:
            raise BacklogError(f"{item_id}: mode must be one of {sorted(SUPPORTED_MODES)}")
        try:
            fanout = tuple(targets_for(raw.get("fanout"), item_id)) if raw.get("fanout") else ()
        except ValueError as exc:
            raise BacklogError(str(exc)) from exc
        output = str(raw.get("output") or "markdown")
        if output not in {"markdown", "json"}:
            raise BacklogError(f"{item_id}: output must be markdown or json")
        bench = raw.get("benchmark") or {}
        if mode == "benchmark" and not (isinstance(bench, Mapping) and bench.get("source_item")):
            raise BacklogError(f"{item_id}: benchmark mode needs benchmark.source_item")
        context = tuple(
            (str(c["repo"]), str(c["path"]))
            for c in raw.get("context") or []
            if isinstance(c, Mapping) and c.get("repo") and c.get("path")
        )
        items.append(
            BacklogItem(
                id=item_id,
                rank=int(raw.get("rank") or 1000),
                line=str(raw.get("line") or ""),
                mode=mode,
                tiers=tiers,
                budget_share=share,
                objective=" ".join(str(raw.get("objective") or "").split()),
                deliverable=" ".join(str(raw.get("deliverable") or "").split()),
                graph=str(raw["graph"]) if raw.get("graph") else None,
                max_output_tokens=int(raw.get("max_output_tokens") or 8000),
                context=context,
                allowed_tools=tools,
                acceptance=tuple(str(a) for a in raw.get("acceptance") or []),
                fanout=fanout,
                refine_rounds=max(0, min(3, int(raw.get("refine_rounds", 0) or 0))),
                depends_on=tuple(str(d) for d in raw.get("depends_on") or []),
                output=output,
                json_min_items=int(raw.get("json_min_items") or 0),
                parallel=max(1, min(6, int(raw.get("parallel") or 2))),
                benchmark=tuple(sorted(bench.items())) if isinstance(bench, Mapping) else (),
            )
        )
    known = {i.id for i in items}
    for it in items:
        missing = [d for d in it.depends_on if d not in known]
        if missing:
            raise BacklogError(f"{it.id}: depends_on unknown item(s) {missing}")
    if total_share > 1.0 + 1e-9:
        raise BacklogError(f"budget shares add up to {total_share:.2f} (> 1.0)")
    return items
