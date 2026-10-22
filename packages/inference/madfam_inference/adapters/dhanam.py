"""Dhanam billing & wealth adapter -- transactions, bank data, payments, economic indicators."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from .financial_reads import (
    CompleteTransactionRead,
    FinancialReadUnavailableError,
    TransactionReadProof,
)

logger = logging.getLogger(__name__)


# --- Response Models ---


class ExchangeRate(BaseModel):
    """Exchange rate data sourced via Dhanam market data API (Banxico-backed)."""

    date: str = ""
    rate: str = ""
    currency_pair: str = "USD/MXN"


class EconomicIndicator(BaseModel):
    """Economic indicator data sourced via Dhanam market data API (Banxico-backed)."""

    series_id: str = ""
    name: str = ""
    date: str = ""
    value: str = ""


class DhanamTransaction(BaseModel):
    """A single financial transaction from Dhanam."""

    id: str
    amount: str
    currency: str = "MXN"
    description: str = ""
    category: str = ""
    date: str = ""
    payment_method: str = ""  # stripe_mx, conekta, oxxo, spei, transfer
    cfdi_uuid: str | None = None
    counterparty_rfc: str | None = None
    status: str = ""


class DhanamBankStatement(BaseModel):
    """Bank account statement sourced via Belvo through Dhanam."""

    account_id: str
    account_name: str = ""
    institution: str = ""  # belvo provider name
    balance: str = ""
    currency: str = "MXN"
    transactions: list[DhanamTransaction] = Field(default_factory=list)


class DhanamPaymentSummary(BaseModel):
    """Aggregated payment summary for a period."""

    period: str = ""
    total_income: str = "0.00"
    total_expenses: str = "0.00"
    by_method: dict[str, str] = Field(default_factory=dict)


# --- Adapter ---


class DhanamAdapter:
    """Async client wrapping the Dhanam billing REST API.

    Uses httpx.AsyncClient for HTTP calls with Bearer token auth.
    Period reads fail closed unless their source completeness can be established.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._read_configured = bool(base_url or os.environ.get("DHANAM_API_URL"))
        self._base_url = (
            base_url or os.environ.get("DHANAM_API_URL", "http://localhost:3060")
        ).rstrip("/")
        self._token = token or os.environ.get("DHANAM_API_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    # -- Transactions -----------------------------------------------------------

    async def list_transactions(
        self,
        org_id: str,
        since: str,
        until: str,
    ) -> CompleteTransactionRead:
        """Read every page for a space and [since, until) UTC date window.

        This proves the paginated response was consumed, not that every source
        statement is ingested, the requested space is legally owned by the user,
        or that the server supplied an immutable snapshot.
        """
        try:
            if not self._read_configured or not self._token or not org_id:
                raise ValueError("Financial source is not configured")
            start = datetime.fromisoformat(since.replace("Z", "+00:00"))
            end = datetime.fromisoformat(until.replace("Z", "+00:00"))
            start = start.replace(tzinfo=UTC) if start.tzinfo is None else start
            end = end.replace(tzinfo=UTC) if end.tzinfo is None else end
            if start >= end:
                raise ValueError("Invalid financial read interval")
            page_size = 100
            expected_total = None
            rows: list[dict[str, Any]] = []
            ids: set[str] = set()
            async with httpx.AsyncClient(timeout=15.0) as client:
                for page in range(1, 10001):
                    response = await client.get(
                        f"{self._base_url}/v1/spaces/{quote(org_id, safe='')}/transactions",
                        headers=self._headers(),
                        params={
                            "startDate": start.isoformat(),
                            "endDate": (end - timedelta(milliseconds=1)).isoformat(),
                            "page": page,
                            "limit": page_size,
                            "sortBy": "createdAt",
                            "sortOrder": "asc",
                        },
                    )
                    response.raise_for_status()
                    body = response.json()
                    if not isinstance(body, dict) or body.get("error"):
                        raise ValueError("Invalid financial read envelope")
                    if (
                        type(body.get("total")) is not int
                        or body["total"] < 0
                        or type(body.get("page")) is not int
                        or body["page"] != page
                        or type(body.get("limit")) is not int
                        or body["limit"] != page_size
                        or not isinstance(body.get("data"), list)
                    ):
                        raise ValueError("Missing pagination proof")
                    if expected_total is None:
                        expected_total = body["total"]
                    if body["total"] != expected_total:
                        raise ValueError("Source count changed during read")
                    batch = body["data"]
                    if len(batch) != min(page_size, expected_total - len(rows)):
                        raise ValueError("Incomplete or oversized financial page")
                    for row in batch:
                        if not isinstance(row, dict):
                            raise ValueError("Invalid transaction row")
                        identifier = row.get("id")
                        if not isinstance(identifier, str) or not identifier or identifier in ids:
                            raise ValueError("Missing or duplicate transaction identity")
                        if (
                            not isinstance(row.get("accountId"), str)
                            or not row["accountId"]
                            or not isinstance(row.get("currency"), str)
                            or not row["currency"]
                            or not isinstance(row.get("date"), str)
                            or isinstance(row.get("amount"), bool)
                            or not Decimal(str(row.get("amount"))).is_finite()
                        ):
                            raise ValueError("Invalid transaction provenance")
                        row_date = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
                        if row_date.tzinfo is None:
                            row_date = row_date.replace(tzinfo=UTC)
                        if not start <= row_date < end:
                            raise ValueError("Source ignored the requested date window")
                        if row.get("spaceId", org_id) != org_id:
                            raise ValueError("Source returned a different space")
                        ids.add(identifier)
                        rows.append(row)
                    if len(rows) == expected_total:
                        return CompleteTransactionRead(
                            items=rows,
                            proof=TransactionReadProof(
                                scope_id=org_id,
                                since=since,
                                until_exclusive=until,
                                total=expected_total,
                                pages_read=page,
                                page_size=page_size,
                            ),
                        )
            raise ValueError("Financial read exceeded its page bound")
        except Exception:
            logger.warning("Dhanam transaction read unavailable or incomplete")
            raise FinancialReadUnavailableError("dhanam_transactions_unavailable") from None

    async def get_bank_statements(self, org_id: str) -> list[DhanamBankStatement]:
        """The legacy bank-accounts route has no verified statement coverage contract."""
        raise FinancialReadUnavailableError("dhanam_statement_contract_unavailable")

    async def get_payment_summary(self, org_id: str, period: str) -> DhanamPaymentSummary:
        """Do not turn a missing summary contract into zero income/expenses."""
        raise FinancialReadUnavailableError("dhanam_payment_summary_contract_unavailable")

    async def get_pos_transactions(
        self,
        org_id: str,
        since: str,
        until: str,
    ) -> list[DhanamTransaction]:
        """The legacy POS route has no verified pagination/period contract."""
        raise FinancialReadUnavailableError("dhanam_pos_contract_unavailable")

    # -- Single transaction (used by billing graph) -----------------------------

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Fetch a single transaction by ID.

        Used by the billing graph to populate CFDI context.

        Returns:
            Raw dict with transaction fields, or empty dict on error.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/transactions/{transaction_id}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Dhanam get_transaction failed: %s", exc)
            return {}

    # -- Economic indicators (Dhanam proxies Banxico internally) ---------------

    async def get_exchange_rate(self, currency: str = "USD") -> ExchangeRate:
        """Get exchange rate via Dhanam market data API.

        Dhanam proxies to Banxico SIE internally so callers do not need
        a direct Banxico dependency.

        Args:
            currency: Currency code (default: USD).

        Returns:
            ExchangeRate with date, rate, and currency_pair.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/market/exchange-rate",
                    headers=self._headers(),
                    params={"currency": currency},
                )
                resp.raise_for_status()
                return ExchangeRate(**resp.json())
        except Exception as exc:
            logger.warning("Dhanam exchange rate fetch failed: %s", exc)
            return ExchangeRate(currency_pair=f"{currency}/MXN")

    async def get_tiie(self, term: str = "28") -> EconomicIndicator:
        """Get TIIE interbank interest rate via Dhanam market data API.

        Args:
            term: Term in days -- ``"28"`` or ``"91"``.

        Returns:
            EconomicIndicator with TIIE value.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/market/tiie",
                    headers=self._headers(),
                    params={"term": term},
                )
                resp.raise_for_status()
                return EconomicIndicator(**resp.json())
        except Exception as exc:
            logger.warning("Dhanam TIIE fetch failed: %s", exc)
            return EconomicIndicator(name=f"TIIE {term} dias")

    async def get_inflation(self) -> EconomicIndicator:
        """Get Mexican CPI (INPC) annual inflation rate via Dhanam market data API.

        Returns:
            EconomicIndicator with annual inflation percentage.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/market/inflation",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return EconomicIndicator(**resp.json())
        except Exception as exc:
            logger.warning("Dhanam inflation fetch failed: %s", exc)
            return EconomicIndicator(name="INPC Variacion Anual")

    async def get_uma(self) -> EconomicIndicator:
        """Get UMA (Unidad de Medida y Actualizacion) daily value via Dhanam.

        The UMA is used across Mexican law as a reference unit for fines,
        social security contributions, and tax thresholds.

        Returns:
            EconomicIndicator with daily UMA value in MXN.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/market/uma",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return EconomicIndicator(**resp.json())
        except Exception as exc:
            logger.warning("Dhanam UMA fetch failed: %s", exc)
            return EconomicIndicator(name="UMA Valor Diario")
