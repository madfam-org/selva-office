"""One sweep: read the ledger window, sync the outbox, send what is due.

The ledger is read through ``tenant_session("platform")``: the strict RLS
policies on ``compute_token_ledger`` honour the ``platform`` marker, so the
sweep sees every org's rows on the regular pool (production sets no
``DATABASE_ADMIN_URL``, so ``admin_session()`` would see none). The marker is
transaction-local, so the read happens first, before any commit.

Only CLOSED civil days are built (America/Mexico_City): by default the
``lookback_days`` days before today, every sweep, so late rows and grant edits
are corrected through the same idempotent ``(source, id)``.
"""

from __future__ import annotations

import logging
import time as _time
from collections import Counter
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import metrics
from . import outbox as ob
from .config import CostEventsConfig, CostEventsConfigError
from .dhanam_client import ALERTS, MAX_BATCH, STOPS_RUN, DhanamCostEventsClient
from .rollup import (
    FundingRules,
    GrantWindow,
    LedgerRow,
    RollupResult,
    civil_day,
    day_bounds_utc,
    rollup,
)

logger = logging.getLogger(__name__)

#: At most this many batches per sweep (500 events each).
MAX_BATCHES_PER_RUN = 40

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class SweepRefusedError(RuntimeError):
    """The sweep may not send: flag off or configuration missing (names only)."""


@dataclass
class RunReport:
    dry_run: bool
    days: list[date]
    rollup: RollupResult
    changes: Counter[str] = field(default_factory=Counter)
    sent: Counter[str] = field(default_factory=Counter)
    pending_after: int = 0
    stopped_on: str = ""

    @property
    def alert(self) -> bool:
        return self.stopped_on in ALERTS

    def summary(self) -> dict[str, Any]:
        """Counts and codes only: no org, no amount, no payload."""
        return {
            "dry_run": self.dry_run,
            "first_day": self.days[0].isoformat() if self.days else None,
            "last_day": self.days[-1].isoformat() if self.days else None,
            "rows_seen": self.rollup.rows_seen,
            "rows_without_provider": self.rollup.rows_without_provider,
            "events_built": len(self.rollup.events),
            "built_by_funding_class": {
                f"{funding}/{cost_class}": n
                for (funding, cost_class), n in sorted(self.rollup.built.items())
            },
            "withheld_events": dict(sorted(self.rollup.withheld_events.items())),
            "withheld_calls": dict(sorted(self.rollup.withheld_calls.items())),
            "withheld_tokens": dict(sorted(self.rollup.withheld_tokens.items())),
            "outbox_changes": dict(sorted(self.changes.items())),
            "sent_events_by_outcome": dict(sorted(self.sent.items())),
            "pending_after": self.pending_after,
            "stopped_on": self.stopped_on or None,
        }


def funding_rules_from_env() -> FundingRules:
    """The grant guard's own view: declared grants, required providers, platform ids.

    An invalid grants file is a configuration error: classifying without it
    would book grant-covered usage as paid.
    """
    from madfam_inference import credentials as cred_lib
    from madfam_inference import grants as grant_lib

    state = grant_lib.load_grant_config()
    if state.error:
        raise CostEventsConfigError("the provider grants config is invalid (see grants logs)")
    return FundingRules(
        grants=tuple(
            GrantWindow(g.provider, g.starts_at, g.expires_at, tuple(g.allowed_orgs))
            for g in state.grants
        ),
        required_providers=grant_lib.required_providers(),
        guard_platform_orgs=grant_lib.platform_org_ids(),
        is_extra_credential=cred_lib.is_extra_credential,
    )


def window(
    cfg: CostEventsConfig,
    today: date,
    since: date | None = None,
    until: date | None = None,
) -> list[date]:
    """Closed civil days to rebuild. ``until`` is capped at yesterday."""
    yesterday = today - timedelta(days=1)
    last = min(until or yesterday, yesterday)
    first = since or (today - timedelta(days=cfg.lookback_days))
    if cfg.start_date and first < cfg.start_date:
        first = cfg.start_date
    if first > last:
        return []
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


async def read_ledger(db: AsyncSession, days: list[date]) -> AsyncIterator[LedgerRow]:
    from ..models import ComputeTokenLedger

    start, _ = day_bounds_utc(days[0])
    _, end = day_bounds_utc(days[-1])
    table = ComputeTokenLedger
    stream = await db.stream(
        select(
            table.created_at,
            table.org_id,
            table.caller,
            table.provider,
            table.amount,
            table.cost_usd,
        )
        .where(table.created_at >= start, table.created_at < end)
        .execution_options(yield_per=2000)
    )
    async for created_at, org_id, caller, provider, amount, cost_usd in stream:
        yield LedgerRow(
            created_at=created_at,
            org_id=org_id or "",
            caller=caller,
            provider=provider,
            amount=int(amount or 0),
            cost_usd=None if cost_usd is None else Decimal(cost_usd),
        )


def _default_session_factory() -> AbstractAsyncContextManager[AsyncSession]:
    from ..database import tenant_session

    return tenant_session("platform")


async def run(
    cfg: CostEventsConfig,
    *,
    dry_run: bool,
    since: date | None = None,
    until: date | None = None,
    replay: bool = False,
    rules: FundingRules | None = None,
    session_factory: SessionFactory | None = None,
    client: DhanamCostEventsClient | None = None,
    now: datetime | None = None,
) -> RunReport:
    """Build (and unless ``dry_run``, store and send) the events of the window."""
    if not dry_run:
        if not cfg.enabled:
            raise SweepRefusedError("SELVA_COST_EVENTS_EMIT_ENABLED is not true")
        missing = cfg.missing_for_send()
        if missing:
            raise SweepRefusedError("missing: " + ", ".join(missing))
    rules = rules if rules is not None else funding_rules_from_env()
    today = civil_day(now or datetime.now(tz=UTC))
    days = window(cfg, today, since, until)
    report = RunReport(dry_run=dry_run, days=days, rollup=RollupResult())
    factory = session_factory or _default_session_factory
    async with factory() as db:
        if days:
            rows = [row async for row in read_ledger(db, days)]
            report.rollup = rollup(rows, cfg, rules, frozenset(days))
            report.changes = await ob.sync_outbox(
                db, report.rollup.events, report.rollup.days, days, replay=replay
            )
        if dry_run:
            # The change counts are what a real sweep would do; nothing is kept.
            report.pending_after = await ob.pending_count(db)
            await db.rollback()
            return report
        await db.commit()
        metrics.record_build(report.rollup.built, report.rollup.withheld_events)
        metrics.record_changes(report.changes)
        await _send(db, client or DhanamCostEventsClient(cfg), report)
        report.pending_after = await ob.pending_count(db)
        await db.commit()
    metrics.record_end(report.pending_after, not report.alert, _time.time())
    return report


async def _send(db: AsyncSession, client: DhanamCostEventsClient, report: RunReport) -> None:
    for _ in range(MAX_BATCHES_PER_RUN):
        rows = await ob.due_rows(db, MAX_BATCH)
        if not rows:
            return
        result = await client.post_batch([row.payload for row in rows])
        if result.ok:
            ob.mark_sent(rows)
            report.sent["ok"] += len(rows)
            metrics.record_sent("ok", len(rows))
        elif result.outcome == "rejected":
            refused = result.index_errors or {i: ["unspecified"] for i in range(len(rows))}
            for index, codes in refused.items():
                if 0 <= index < len(rows):
                    ob.mark_rejected(rows[index], codes)
            report.sent["rejected"] += len(refused)
            metrics.record_sent("rejected", len(refused))
        else:
            ob.mark_retry(rows, result.error_code or result.outcome)
            report.sent[result.outcome] += len(rows)
            metrics.record_sent(result.outcome, len(rows))
        await db.commit()
        if result.outcome in STOPS_RUN:
            report.stopped_on = result.outcome
            return
