"""Monthly inference usage of one org, read from ``ComputeTokenLedger``.

The single source for both ``GET /api/v1/billing/inference-usage`` and the
MCP tool ``inference_usage`` (``nexus_api.mcp``): the tool calls this function
with the org of its verified token, exactly as the HTTP route does with the
org of its caller.

Which rows count: ``action`` ``inference_proxy`` (the inference proxy,
``services/inference_usage_ledger.py``) and ``inference`` (worker metering
through ``POST /api/v1/billing/record``). Other ledger actions (task dispatch,
CRM sends, deploys) are token-budget debits, not model calls.

The period is the civil month in ``America/Mexico_City``, the cost ledger's
period cut-off. See ``schemas/inference_usage.py`` for the wording rules
(list-price estimate, funding unattributed, unknown = null).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ComputeTokenLedger
from ..schemas.inference_usage import (
    CallerClass,
    Completeness,
    CompletenessStatus,
    GapCode,
    InferenceUsageReport,
    ListPriceEstimate,
    TokenTotals,
    UsageLine,
    UsagePeriod,
)

#: Ledger actions that record a model call.
INFERENCE_ACTIONS: tuple[str, ...] = ("inference_proxy", "inference")
LEDGER_TZ = ZoneInfo("America/Mexico_City")
MONTH_PATTERN = r"^(20[0-9]{2})-(0[1-9]|1[0-2])$"
_MONTH_RE = re.compile(MONTH_PATTERN)
_USD_QUANTUM = Decimal("0.000001")
#: Janua ``client_credentials`` subjects (machine clients).
_SERVICE_ACCOUNT_PREFIX = "service-account:"
#: Selva's own worker / gateway identities (``auth.get_current_user``).
_SELVA_SERVICE_PREFIX = "service:"


class InvalidMonthError(ValueError):
    """``month`` is not ``YYYY-MM`` or lies in the future. ``code`` is stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def month_bounds(month: str, now: datetime | None = None) -> UsagePeriod:
    """``YYYY-MM`` → its bounds in the ledger's timezone; future months are refused."""
    match = _MONTH_RE.fullmatch(month or "")
    if match is None:
        raise InvalidMonthError("invalid_month", "month must be YYYY-MM (2000-01 .. 2099-12)")
    year, mon = int(match.group(1)), int(match.group(2))
    start = datetime(year, mon, 1, tzinfo=LEDGER_TZ)
    end = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=LEDGER_TZ)
    current = (now or datetime.now(UTC)).astimezone(LEDGER_TZ)
    if start > current:
        raise InvalidMonthError("month_in_future", "month has not started yet")
    return UsagePeriod(month=month, start=start, end=end, month_closed=current >= end)


def caller_class(caller: str | None, action: str) -> CallerClass:
    """Who made the call, as a class. Never the identity: a person's subject is personal data."""
    if caller and caller.startswith(_SERVICE_ACCOUNT_PREFIX):
        return "service_account"
    if caller and caller.startswith(_SELVA_SERVICE_PREFIX):
        return "selva_worker"
    if caller and caller != "unknown":
        return "person"
    # Worker metering (POST /billing/record, action "inference") stores no caller.
    if caller is None and action == "inference":
        return "selva_worker"
    return "unrecorded"


def _usd(value: Decimal | None) -> str | None:
    return None if value is None else str(Decimal(value).quantize(_USD_QUANTUM))


@dataclass
class _Group:
    rows: int = 0
    tokens: int = 0
    priced: Decimal | None = None
    unpriced: int = 0

    def add(self, rows: int, tokens: int, priced_rows: int, usd: Decimal | None) -> None:
        self.rows += rows
        self.tokens += tokens
        self.unpriced += rows - priced_rows
        if priced_rows:
            self.priced = (self.priced or Decimal(0)) + Decimal(usd or 0)


async def build_inference_usage_report(
    db: AsyncSession, *, org_id: str, month: str, now: datetime | None = None
) -> InferenceUsageReport:
    """Aggregate the org's inference rows for ``month``. Raises ``InvalidMonthError``."""
    period = month_bounds(month, now)
    # Stored timestamps are UTC; compare against UTC instants of the bounds.
    start_utc, end_utc = period.start.astimezone(UTC), period.end.astimezone(UTC)
    ledger = ComputeTokenLedger
    result = await db.execute(
        select(
            ledger.provider,
            ledger.model,
            ledger.caller,
            ledger.action,
            func.count(ledger.id),
            func.coalesce(func.sum(ledger.amount), 0),
            func.count(ledger.cost_usd),
            func.sum(ledger.cost_usd),
        )
        .where(ledger.org_id == org_id)
        .where(ledger.action.in_(INFERENCE_ACTIONS))
        .where(ledger.created_at >= start_utc)
        .where(ledger.created_at < end_utc)
        .group_by(ledger.provider, ledger.model, ledger.caller, ledger.action)
    )
    groups: dict[tuple[str | None, str | None, CallerClass], _Group] = defaultdict(_Group)
    for provider, model, caller, action, rows, tokens, priced_rows, usd in result.all():
        key = (provider, model, caller_class(caller, action))
        groups[key].add(int(rows), int(tokens), int(priced_rows), usd)

    total = _Group()
    lines: list[UsageLine] = []
    for (provider, model, klass), group in sorted(
        groups.items(), key=lambda item: (-item[1].tokens, str(item[0]))
    ):
        priced_rows = group.rows - group.unpriced
        total.add(group.rows, group.tokens, priced_rows, group.priced)
        lines.append(
            UsageLine(
                provider=provider,
                model=model,
                caller_class=klass,
                request_count=group.rows,
                tokens=TokenTotals(total=group.tokens),
                list_price_estimate_usd=_usd(group.priced),
                unpriced_rows=group.unpriced,
            )
        )

    empty = total.rows == 0
    gaps: list[GapCode] = []
    if not period.month_closed:
        gaps.append("month_open")
    if total.unpriced:
        gaps.append("unpriced_rows")
    if empty:
        gaps.append("no_rows")
    status: CompletenessStatus = "empty" if empty else ("partial" if gaps else "complete")

    return InferenceUsageReport(
        org=org_id,
        period=period,
        status="empty" if empty else "ok",
        ledger_rows=total.rows,
        request_count=None if empty else total.rows,
        tokens=TokenTotals(total=None if empty else total.tokens),
        by_line=lines,
        list_price_estimate_usd=_usd(total.priced),
        estimate=ListPriceEstimate(
            priced_rows=total.rows - total.unpriced,
            unpriced_rows=total.unpriced,
            is_lower_bound=total.unpriced > 0 and total.priced is not None,
        ),
        completeness=Completeness(status=status, gaps=gaps),
    )
