"""Prometheus metrics of the cost-events emitter (no-ops without ``prometheus_client``).

Registered in the process that runs the sweep. The scheduled sweep is a
short-lived Job, so its durable signals are the one-line ``summary`` log and
the exit code (non-zero on an operator problem, which fails the Job); these
counters matter when the sweep runs inside a long-lived process.
"""

from __future__ import annotations

from collections.abc import Mapping

try:
    from prometheus_client import Counter, Gauge

    EVENTS_BUILT = Counter(
        "selva_cost_events_built_total",
        "cost.event.v1 events built from the inference ledger, by funding and cost class.",
        ["funding", "cost_class"],
    )
    EVENTS_WITHHELD = Counter(
        "selva_cost_events_withheld_total",
        "Would-be events not sent, by reason (local_compute, grant_memo_unsupported, "
        "funding_unknown, unpriced, below_one_cent).",
        ["reason"],
    )
    OUTBOX_CHANGES = Counter(
        "selva_cost_events_outbox_changes_total",
        "Outbox rows created, updated, cancelled, deleted or unchanged by a sweep.",
        ["change"],
    )
    EVENTS_SENT = Counter(
        "selva_cost_events_sent_total",
        "Events posted to Dhanam, by batch outcome.",
        ["outcome"],
    )
    OUTBOX_PENDING = Gauge(
        "selva_cost_events_outbox_pending",
        "Outbox rows still waiting for Dhanam after the last sweep.",
    )
    LAST_SUCCESS = Gauge(
        "selva_cost_events_last_success_timestamp_seconds",
        "Unix time of the last sweep that ended without an operator problem.",
    )
    _ENABLED = True
except ImportError:  # pragma: no cover - only without the dependency
    _ENABLED = False


def record_build(built: Mapping[tuple[str, str], int], withheld: Mapping[str, int]) -> None:
    if not _ENABLED:
        return
    for (funding, cost_class), count in built.items():
        EVENTS_BUILT.labels(funding=funding, cost_class=cost_class).inc(count)
    for reason, count in withheld.items():
        EVENTS_WITHHELD.labels(reason=reason).inc(count)


def record_changes(changes: Mapping[str, int]) -> None:
    if not _ENABLED:
        return
    for change, count in changes.items():
        OUTBOX_CHANGES.labels(change=change).inc(count)


def record_sent(outcome: str, count: int) -> None:
    if _ENABLED and count:
        EVENTS_SENT.labels(outcome=outcome).inc(count)


def record_end(pending: int, success: bool, now: float) -> None:
    if not _ENABLED:
        return
    OUTBOX_PENDING.set(pending)
    if success:
        LAST_SUCCESS.set(now)
