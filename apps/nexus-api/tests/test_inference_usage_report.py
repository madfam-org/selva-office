"""Monthly inference usage: the service and ``GET /api/v1/billing/inference-usage``.

Synthetic orgs and callers only. The dev-auth bypass in the test settings
authenticates HTTP calls as org ``dev-org``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.models import ComputeTokenLedger
from nexus_api.services.inference_usage_report import (
    InvalidMonthError,
    build_inference_usage_report,
    caller_class,
    month_bounds,
)

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=UTC)


def _row(
    org: str = "org-a",
    *,
    at: datetime = datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    action: str = "inference_proxy",
    amount: int = 1000,
    cost: str | None = "0.010000",
    caller: str | None = "service-account:synthetic-quoting",
    provider: str | None = "anthropic",
    model: str | None = "claude-haiku-4-5",
) -> ComputeTokenLedger:
    return ComputeTokenLedger(
        org_id=org,
        action=action,
        amount=amount,
        cost_usd=Decimal(cost) if cost is not None else None,
        caller=caller,
        provider=provider,
        model=model,
        created_at=at,
    )


async def _seed(db: AsyncSession, *rows: ComputeTokenLedger) -> None:
    db.add_all(rows)
    await db.commit()


class TestMonthBounds:
    def test_bounds_follow_mexico_city(self) -> None:
        period = month_bounds("2026-09", NOW)
        assert period.start.isoformat() == "2026-09-01T00:00:00-06:00"
        assert period.end.isoformat() == "2026-10-01T00:00:00-06:00"
        assert period.month_closed is True

    def test_december_rolls_the_year(self) -> None:
        period = month_bounds("2025-12", NOW)
        assert period.end.year == 2026 and period.end.month == 1

    def test_current_month_is_open(self) -> None:
        assert month_bounds("2026-11", NOW).month_closed is False

    @pytest.mark.parametrize("month", ["2026-13", "2026-1", "26-09", "2026-09-01", "", "1999-12"])
    def test_malformed_month_refused(self, month: str) -> None:
        with pytest.raises(InvalidMonthError) as exc:
            month_bounds(month, NOW)
        assert exc.value.code == "invalid_month"

    def test_future_month_refused(self) -> None:
        with pytest.raises(InvalidMonthError) as exc:
            month_bounds("2026-12", NOW)
        assert exc.value.code == "month_in_future"


class TestCallerClass:
    @pytest.mark.parametrize(
        ("caller", "action", "expected"),
        [
            ("service-account:synthetic-quoting", "inference_proxy", "service_account"),
            ("service:worker", "inference_proxy", "selva_worker"),
            (None, "inference", "selva_worker"),
            ("3f0c-user-subject", "inference_proxy", "person"),
            ("unknown", "inference_proxy", "unrecorded"),
            (None, "inference_proxy", "unrecorded"),
        ],
    )
    def test_classes(self, caller: str | None, action: str, expected: str) -> None:
        assert caller_class(caller, action) == expected


class TestReport:
    async def test_aggregates_by_model_and_caller_class(self, db_session: AsyncSession) -> None:
        await _seed(
            db_session,
            _row(amount=1000, cost="0.010000"),
            _row(amount=500, cost="0.005000"),
            _row(action="inference", caller=None, amount=200, cost="0.002000"),
            _row(caller="person-subject-1", model="claude-sonnet-4-6", amount=300, cost="0.030000"),
        )
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-09", now=NOW
        )
        assert report.status == "ok"
        assert report.request_count == 4 and report.ledger_rows == 4
        assert report.tokens.total == 2000
        assert report.tokens.input is None and report.tokens.output is None
        assert report.list_price_estimate_usd == "0.047000"
        assert report.completeness.status == "complete" and report.completeness.gaps == []
        lines = {(line.model, line.caller_class): line for line in report.by_line}
        assert lines[("claude-haiku-4-5", "service_account")].request_count == 2
        assert lines[("claude-haiku-4-5", "service_account")].tokens.total == 1500
        assert lines[("claude-haiku-4-5", "selva_worker")].tokens.total == 200
        assert lines[("claude-sonnet-4-6", "person")].list_price_estimate_usd == "0.030000"

    async def test_no_caller_identity_in_output(self, db_session: AsyncSession) -> None:
        await _seed(db_session, _row(caller="person-subject-1"))
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-09", now=NOW
        )
        dumped = report.model_dump_json()
        assert "person-subject-1" not in dumped
        assert "synthetic-quoting" not in dumped

    async def test_estimate_is_labelled_never_cash(self, db_session: AsyncSession) -> None:
        await _seed(db_session, _row())
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-09", now=NOW
        )
        assert report.estimate.basis == "list_price_estimate"
        assert report.estimate.currency == "USD"
        assert report.estimate.is_cash is False
        assert report.estimate.price_table.version is None
        assert report.funding.status == "unattributed"
        dumped = report.model_dump(mode="json")
        assert "cost" not in " ".join(dumped.keys()) and "cogs" not in " ".join(dumped.keys())

    async def test_other_orgs_and_actions_and_months_excluded(
        self, db_session: AsyncSession
    ) -> None:
        await _seed(
            db_session,
            _row(),
            _row(org="org-b", amount=9999),
            _row(action="dispatch_task", amount=7777, cost=None),
            _row(at=datetime(2026, 10, 1, 7, 0, tzinfo=UTC), amount=8888),  # 01:00 CDMX, October
            _row(at=datetime(2026, 10, 1, 5, 0, tzinfo=UTC), amount=11),  # 23:00 CDMX, Sep 30
        )
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-09", now=NOW
        )
        assert report.request_count == 2
        assert report.tokens.total == 1011

    async def test_unpriced_rows_make_a_lower_bound(self, db_session: AsyncSession) -> None:
        await _seed(db_session, _row(cost="0.010000"), _row(action="inference", cost=None))
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-09", now=NOW
        )
        assert report.list_price_estimate_usd == "0.010000"
        assert report.estimate.unpriced_rows == 1 and report.estimate.is_lower_bound is True
        assert report.completeness.status == "partial"
        assert report.completeness.gaps == ["unpriced_rows"]

    async def test_all_unpriced_is_null_not_zero(self, db_session: AsyncSession) -> None:
        await _seed(db_session, _row(cost=None), _row(cost=None))
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-09", now=NOW
        )
        assert report.list_price_estimate_usd is None
        assert report.by_line[0].list_price_estimate_usd is None
        assert report.estimate.is_lower_bound is False
        assert report.tokens.total == 2000

    async def test_empty_month_is_explicit_not_zeros(self, db_session: AsyncSession) -> None:
        await _seed(db_session, _row(org="org-b"))
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-09", now=NOW
        )
        assert report.status == "empty"
        assert report.ledger_rows == 0
        assert report.request_count is None
        assert report.tokens.total is None
        assert report.list_price_estimate_usd is None
        assert report.by_line == []
        assert report.completeness.status == "empty"
        assert "no_rows" in report.completeness.gaps

    async def test_open_month_is_partial(self, db_session: AsyncSession) -> None:
        await _seed(db_session, _row(at=datetime(2026, 11, 3, 12, 0, tzinfo=UTC)))
        report = await build_inference_usage_report(
            db_session, org_id="org-a", month="2026-11", now=NOW
        )
        assert report.period.month_closed is False
        assert report.completeness.status == "partial"
        assert report.completeness.gaps == ["month_open"]


class TestHttpRead:
    async def test_reads_the_callers_org(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        await _seed(db_session, _row(org="dev-org"), _row(org="org-b", amount=5))
        resp = await client.get(
            "/api/v1/billing/inference-usage", params={"month": "2026-09"}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["org"] == "dev-org"
        assert body["tokens"]["total"] == 1000
        assert body["list_price_estimate_usd"] == "0.010000"
        assert body["funding"]["status"] == "unattributed"

    async def test_other_org_is_forbidden(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.get(
            "/api/v1/billing/inference-usage",
            params={"month": "2026-09", "org": "org-b"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_own_org_named_explicitly(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.get(
            "/api/v1/billing/inference-usage",
            params={"month": "2026-09", "org": "dev-org"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "empty"

    @pytest.mark.parametrize("month", ["2026-13", "september", "2099-01"])
    async def test_bad_month_is_422(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str], month: str
    ) -> None:
        resp = await client.get(
            "/api/v1/billing/inference-usage", params={"month": month}, headers=auth_headers
        )
        assert resp.status_code == 422
