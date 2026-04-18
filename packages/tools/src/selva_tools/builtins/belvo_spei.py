"""Belvo SPEI tools — Mexican bank-transfer initiation + status.

Closes the agent-to-payment-rail gap for MX flows. Our existing
``accounting`` tools compute reconciliations and surfaces payment summaries;
this module actually executes transfers. Belvo's Payments API (powered by
Banxico's SPEI network) lets us move MXN between CLABEs in near real-time
on banking hours and with next-business-day settlement for holds.

Why Belvo specifically: Banxico does not expose SPEI directly — every
originator must go through a Participant or a regulated aggregator. Belvo's
Payment Initiation product is CNBV-registered and supports both sandbox
and production transfers with the same API shape, which matters for
test-in-prod confidence.

Credentials: ``BELVO_SECRET_ID`` (basic-auth user), ``BELVO_SECRET_PASSWORD``
(basic-auth pass), ``BELVO_ENV`` (``sandbox`` default / ``production``).
All tools fail closed when any is missing.

HITL note: money movement is high-reversibility-cost. Skills that use
``spei_transfer_initiate`` must gate it — this module does not gate by
itself (tool-level gating is the permission engine's job).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

BELVO_SECRET_ID = os.environ.get("BELVO_SECRET_ID", "")
BELVO_SECRET_PASSWORD = os.environ.get("BELVO_SECRET_PASSWORD", "")
BELVO_ENV = os.environ.get("BELVO_ENV", "sandbox").lower()


def _base_url() -> str:
    if BELVO_ENV == "production":
        return "https://api.belvo.com"
    return "https://sandbox.belvo.com"


def _creds_check() -> str | None:
    if not BELVO_SECRET_ID:
        return "BELVO_SECRET_ID must be set."
    if not BELVO_SECRET_PASSWORD:
        return "BELVO_SECRET_PASSWORD must be set."
    if BELVO_ENV not in ("sandbox", "production"):
        return f"BELVO_ENV must be 'sandbox' or 'production' (got {BELVO_ENV!r})."
    return None


def _auth() -> tuple[str, str]:
    return (BELVO_SECRET_ID, BELVO_SECRET_PASSWORD)


async def _request(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method, url, auth=_auth(), json=json_body, params=params
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    # Belvo errors come back as {detail, code, message} or a list of such.
    if isinstance(body, list) and body and isinstance(body[0], dict):
        first = body[0]
        return first.get("message") or first.get("detail") or str(first)
    if isinstance(body, dict):
        return (
            body.get("detail")
            or body.get("message")
            or body.get("error")
            or str(body)
        )
    return f"HTTP {status}: {body}"


# ---------------------------------------------------------------------------
# transfer initiate
# ---------------------------------------------------------------------------


class SpeiTransferInitiateTool(BaseTool):
    """Initiate an SPEI transfer from a linked account to a CLABE beneficiary."""

    name = "spei_transfer_initiate"
    description = (
        "Initiate an SPEI transfer. ``amount_cents`` is MXN centavos (int) "
        "to avoid float precision bugs — we convert to the decimal string "
        "Belvo expects. ``concept`` and ``reference`` are required by "
        "Banxico: concept is free-text (max 40 chars), reference is a "
        "7-digit numeric string the receiver reconciles on. Returns "
        "``transaction_id`` for spei_transfer_status polling. Reversibility "
        "is effectively none once SPEI clears — HITL-gate at the skill."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "from_account_link_id": {
                    "type": "string",
                    "description": "Belvo link_id for the source account.",
                },
                "to_clabe": {
                    "type": "string",
                    "description": "18-digit destination CLABE.",
                },
                "amount_cents": {
                    "type": "integer",
                    "description": "Amount in MXN centavos (e.g. 150000 = $1,500.00).",
                    "minimum": 1,
                },
                "concept": {
                    "type": "string",
                    "description": "Free-text concept. Max 40 chars per Banxico.",
                },
                "reference": {
                    "type": "string",
                    "description": "7-digit numeric reference string.",
                },
            },
            "required": [
                "from_account_link_id",
                "to_clabe",
                "amount_cents",
                "concept",
                "reference",
            ],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        clabe = kwargs["to_clabe"]
        if not (clabe.isdigit() and len(clabe) == 18):
            return ToolResult(
                success=False,
                error="to_clabe must be an 18-digit numeric CLABE.",
            )
        ref = kwargs["reference"]
        if not (ref.isdigit() and len(ref) == 7):
            return ToolResult(
                success=False,
                error="reference must be a 7-digit numeric string (Banxico rule).",
            )
        concept = kwargs["concept"]
        if len(concept) > 40:
            return ToolResult(
                success=False,
                error="concept max 40 chars (Banxico rule).",
            )
        cents = int(kwargs["amount_cents"])
        amount_str = f"{cents // 100}.{cents % 100:02d}"
        payload: dict[str, Any] = {
            "link": kwargs["from_account_link_id"],
            "beneficiary_clabe": clabe,
            "amount": amount_str,
            "concept": concept,
            "reference": ref,
            "currency": "MXN",
        }
        try:
            status, body = await _request(
                "POST", "/payments/transfers/", json_body=payload
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"SPEI transfer initiated: transaction_id={body.get('id')} "
                    f"status={body.get('status')} amount={amount_str} MXN"
                ),
                data={
                    "transaction_id": body.get("id"),
                    "status": body.get("status"),
                    "amount": amount_str,
                    "to_clabe": clabe,
                    "reference": ref,
                },
            )
        except Exception as e:
            logger.error("spei_transfer_initiate failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# transfer status
# ---------------------------------------------------------------------------


class SpeiTransferStatusTool(BaseTool):
    """Poll status of a previously-initiated SPEI transfer."""

    name = "spei_transfer_status"
    description = (
        "Fetch the current status of an SPEI transfer by transaction_id. "
        "Typical lifecycle: pending → processing → completed (or failed, "
        "canceled). For completed transfers Belvo returns the Banxico "
        "tracking key (``tracking_key``) which can be verified on "
        "https://www.banxico.org.mx/cep/."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "transaction_id": {"type": "string"},
            },
            "required": ["transaction_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        tid = kwargs["transaction_id"]
        try:
            status, body = await _request(
                "GET", f"/payments/transfers/{tid}/"
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"{tid}: {body.get('status')}",
                data={
                    "transaction_id": body.get("id"),
                    "status": body.get("status"),
                    "amount": body.get("amount"),
                    "tracking_key": body.get("tracking_key"),
                    "created_at": body.get("created_at"),
                    "completed_at": body.get("completed_at"),
                },
            )
        except Exception as e:
            logger.error("spei_transfer_status failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# beneficiary create
# ---------------------------------------------------------------------------


class SpeiBeneficiaryCreateTool(BaseTool):
    """Create a reusable SPEI beneficiary record."""

    name = "spei_beneficiary_create"
    description = (
        "Create a reusable beneficiary (CLABE + name, optional RFC). "
        "Beneficiary IDs can be passed to spei_transfer_initiate as a "
        "substitute for the raw CLABE and survive CLABE re-use audits. "
        "Same CLABE re-submitted returns the existing beneficiary_id."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "clabe": {"type": "string"},
                "name": {"type": "string"},
                "rfc": {
                    "type": "string",
                    "description": "Optional RFC (for CFDI reconciliation).",
                },
            },
            "required": ["clabe", "name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        clabe = kwargs["clabe"]
        if not (clabe.isdigit() and len(clabe) == 18):
            return ToolResult(
                success=False,
                error="clabe must be an 18-digit numeric CLABE.",
            )
        payload: dict[str, Any] = {
            "clabe": clabe,
            "name": kwargs["name"],
        }
        if kwargs.get("rfc"):
            payload["rfc"] = kwargs["rfc"]
        try:
            status, body = await _request(
                "POST", "/payments/beneficiaries/", json_body=payload
            )
            if status >= 400 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Beneficiary recorded: id={body.get('id')} "
                    f"clabe={clabe} name={kwargs['name']}"
                ),
                data={
                    "beneficiary_id": body.get("id"),
                    "clabe": clabe,
                    "name": kwargs["name"],
                    "rfc": kwargs.get("rfc"),
                },
            )
        except Exception as e:
            logger.error("spei_beneficiary_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# balance
# ---------------------------------------------------------------------------


class SpeiAccountBalanceTool(BaseTool):
    """Current MXN balance of a linked account."""

    name = "spei_account_balance"
    description = (
        "Fetch the current balance of a linked Belvo account. Returns "
        "both ``current`` (settled) and ``available`` (settled minus holds) "
        "in MXN."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_link_id": {"type": "string"},
            },
            "required": ["account_link_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        link_id = kwargs["account_link_id"]
        try:
            status, body = await _request(
                "GET", "/api/accounts/", params={"link": link_id}
            )
            if status >= 400:
                return ToolResult(success=False, error=_err(status, body))
            # Accounts endpoint can return a list or paged dict depending on
            # the Belvo API tier; normalise.
            if isinstance(body, dict) and "results" in body:
                items = body.get("results") or []
            elif isinstance(body, list):
                items = body
            else:
                items = []
            if not items:
                return ToolResult(
                    success=False,
                    error=f"No accounts found for link {link_id}.",
                )
            # Sum across accounts under the link (mirrors how Belvo links
            # chequing + savings under one login).
            current = 0.0
            available = 0.0
            currencies = set()
            for acct in items:
                bal = (acct.get("balance") or {}) if isinstance(acct, dict) else {}
                try:
                    current += float(bal.get("current") or 0.0)
                    available += float(bal.get("available") or 0.0)
                except (TypeError, ValueError):
                    pass
                if acct.get("currency"):
                    currencies.add(acct["currency"])
            return ToolResult(
                success=True,
                output=(
                    f"Link {link_id}: current={current:.2f} "
                    f"available={available:.2f} MXN"
                ),
                data={
                    "account_link_id": link_id,
                    "current": round(current, 2),
                    "available": round(available, 2),
                    "currency": next(iter(currencies), "MXN"),
                    "account_count": len(items),
                },
            )
        except Exception as e:
            logger.error("spei_account_balance failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# transaction list
# ---------------------------------------------------------------------------


class SpeiTransactionListTool(BaseTool):
    """List transactions over a time window."""

    name = "spei_transaction_list"
    description = (
        "List transactions on a linked account between ``since`` and "
        "``until`` (YYYY-MM-DD). Used for reconciliation loops: compare "
        "Belvo's view of cleared transfers against our internal ledger."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_link_id": {"type": "string"},
                "since": {"type": "string", "description": "YYYY-MM-DD."},
                "until": {"type": "string", "description": "YYYY-MM-DD."},
                "limit": {"type": "integer", "default": 100, "maximum": 1000},
            },
            "required": ["account_link_id", "since", "until"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        params: dict[str, Any] = {
            "link": kwargs["account_link_id"],
            "date_from": kwargs["since"],
            "date_to": kwargs["until"],
            "page_size": min(int(kwargs.get("limit", 100)), 1000),
        }
        try:
            status, body = await _request(
                "GET", "/api/transactions/", params=params
            )
            if status >= 400:
                return ToolResult(success=False, error=_err(status, body))
            if isinstance(body, dict) and "results" in body:
                items = body.get("results") or []
            elif isinstance(body, list):
                items = body
            else:
                items = []
            summary = [
                {
                    "id": t.get("id"),
                    "value_date": t.get("value_date"),
                    "amount": t.get("amount"),
                    "currency": t.get("currency"),
                    "type": t.get("type"),
                    "description": (t.get("description") or "")[:200],
                    "reference": t.get("reference"),
                    "status": t.get("status"),
                }
                for t in items
            ]
            return ToolResult(
                success=True,
                output=f"Found {len(summary)} transaction(s).",
                data={"transactions": summary},
            )
        except Exception as e:
            logger.error("spei_transaction_list failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_belvo_spei_tools() -> list[BaseTool]:
    """Return the Belvo SPEI tool set."""
    return [
        SpeiTransferInitiateTool(),
        SpeiTransferStatusTool(),
        SpeiBeneficiaryCreateTool(),
        SpeiAccountBalanceTool(),
        SpeiTransactionListTool(),
    ]
