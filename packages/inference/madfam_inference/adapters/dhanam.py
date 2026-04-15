"""Dhanam billing & wealth adapter -- transactions, bank data, payments."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --- Response Models ---


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
    All methods return typed Pydantic models and degrade gracefully on error.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("DHANAM_API_URL", "http://localhost:3060")
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
    ) -> list[DhanamTransaction]:
        """List transactions for an org within a date range.

        Args:
            org_id: Organization identifier (Dhanam space).
            since: ISO-8601 start date (inclusive).
            until: ISO-8601 end date (inclusive).

        Returns:
            List of DhanamTransaction models.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/spaces/{org_id}/transactions",
                    headers=self._headers(),
                    params={"since": since, "until": until},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [DhanamTransaction(**t) for t in data]
                return []
        except Exception as exc:
            logger.warning("Dhanam list_transactions failed: %s", exc)
            return []

    # -- Bank statements --------------------------------------------------------

    async def get_bank_statements(
        self,
        org_id: str,
    ) -> list[DhanamBankStatement]:
        """Fetch bank account statements (Belvo-sourced) for an org.

        Args:
            org_id: Organization identifier (Dhanam space).

        Returns:
            List of DhanamBankStatement models.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/spaces/{org_id}/bank-accounts",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [DhanamBankStatement(**s) for s in data]
                return []
        except Exception as exc:
            logger.warning("Dhanam get_bank_statements failed: %s", exc)
            return []

    # -- Payment summary --------------------------------------------------------

    async def get_payment_summary(
        self,
        org_id: str,
        period: str,
    ) -> DhanamPaymentSummary:
        """Get aggregated payment summary for a period.

        Args:
            org_id: Organization identifier (Dhanam space).
            period: Period string (e.g. ``"2026-04"``).

        Returns:
            DhanamPaymentSummary with income/expense totals and per-method breakdown.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/spaces/{org_id}/payments/summary",
                    headers=self._headers(),
                    params={"period": period},
                )
                resp.raise_for_status()
                return DhanamPaymentSummary(**resp.json())
        except Exception as exc:
            logger.warning("Dhanam get_payment_summary failed: %s", exc)
            return DhanamPaymentSummary(period=period)

    # -- POS transactions -------------------------------------------------------

    async def get_pos_transactions(
        self,
        org_id: str,
        since: str,
        until: str,
    ) -> list[DhanamTransaction]:
        """Fetch POS transactions (Stripe MX terminal / Conekta POS).

        Args:
            org_id: Organization identifier (Dhanam space).
            since: ISO-8601 start date (inclusive).
            until: ISO-8601 end date (inclusive).

        Returns:
            List of DhanamTransaction from POS channels.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/spaces/{org_id}/pos-transactions",
                    headers=self._headers(),
                    params={"since": since, "until": until},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [DhanamTransaction(**t) for t in data]
                return []
        except Exception as exc:
            logger.warning("Dhanam get_pos_transactions failed: %s", exc)
            return []

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
