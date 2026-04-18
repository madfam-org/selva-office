"""Dhanam tenant provisioning tools.

Dhanam's tenant abstraction is the ``space``. Every onboarded tenant gets:
- One ``space`` (the financial tenant)
- One subscription row pinning the plan + credit ceiling
- Optional Stripe Customer mapping for outbound billing

API base: ``DHANAM_API_URL`` (default ``https://api.dhanam.app/v1``).
Auth: ``DHANAM_ADMIN_TOKEN`` (bearer, service-role).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

DHANAM_API_URL = os.environ.get("DHANAM_API_URL", "https://api.dhanam.app/v1")
DHANAM_ADMIN_TOKEN = os.environ.get("DHANAM_ADMIN_TOKEN", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DHANAM_ADMIN_TOKEN}",
        "Content-Type": "application/json",
    }


def _creds_check() -> str | None:
    if not DHANAM_ADMIN_TOKEN:
        return "DHANAM_ADMIN_TOKEN must be set."
    return None


async def _request(
    method: str, path: str, json_body: dict[str, Any] | None = None
) -> tuple[int, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method,
            f"{DHANAM_API_URL.rstrip('/')}{path}",
            headers=_headers(),
            json=json_body,
        )
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text


def _ok(s: int) -> bool:
    return 200 <= s < 300


def _err(s: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("message") or body.get("detail") or str(body)
    return f"HTTP {s}: {body}"


class DhanamSpaceCreateTool(BaseTool):
    """Create a Dhanam space (the tenant)."""

    name = "dhanam_space_create"
    description = (
        "Create a Dhanam 'space' — the financial tenant. Each onboarded "
        "customer gets exactly one. Returns the space_id that every "
        "subsequent Dhanam API call must carry."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["personal", "business"],
                    "default": "business",
                },
                "currency": {"type": "string", "default": "MXN"},
                "metadata": {"type": "object"},
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        payload = {
            "name": kwargs["name"],
            "type": kwargs.get("type", "business"),
            "currency": kwargs.get("currency", "MXN"),
            "metadata": kwargs.get("metadata") or {},
        }
        try:
            status, body = await _request("POST", "/spaces", json_body=payload)
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"Space created: {body.get('name')} ({body.get('id')}).",
                data={"space_id": body.get("id"), "name": body.get("name")},
            )
        except Exception as e:
            logger.error("dhanam_space_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


class DhanamSubscriptionCreateTool(BaseTool):
    """Attach a subscription to a space."""

    name = "dhanam_subscription_create"
    description = (
        "Attach a subscription to a Dhanam space. Pins the plan + credit "
        "ceiling that gates downstream agent inference cost. Plans are "
        "defined in the Dhanam catalog.yaml."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "space_id": {"type": "string"},
                "plan_id": {
                    "type": "string",
                    "description": "Plan slug (e.g. 'starter', 'growth', 'enterprise').",
                },
                "credit_ceiling_cents": {
                    "type": "integer",
                    "description": "Hard monthly credit cap in cents.",
                },
                "billing_cycle": {
                    "type": "string",
                    "enum": ["monthly", "annual"],
                    "default": "monthly",
                },
                "trial_days": {"type": "integer", "default": 0},
            },
            "required": ["space_id", "plan_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        payload = {
            "plan_id": kwargs["plan_id"],
            "credit_ceiling_cents": kwargs.get("credit_ceiling_cents"),
            "billing_cycle": kwargs.get("billing_cycle", "monthly"),
            "trial_days": kwargs.get("trial_days", 0),
        }
        sid = kwargs["space_id"]
        try:
            status, body = await _request(
                "POST", f"/spaces/{sid}/subscriptions", json_body=payload
            )
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Subscription created on space {sid}: "
                    f"plan={body.get('plan_id')}"
                ),
                data={
                    "subscription_id": body.get("id"),
                    "space_id": sid,
                    "plan_id": body.get("plan_id"),
                    "status": body.get("status"),
                },
            )
        except Exception as e:
            logger.error("dhanam_subscription_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


class DhanamSubscriptionUpdateTool(BaseTool):
    """Update plan / credit ceiling on an existing subscription."""

    name = "dhanam_subscription_update"
    description = (
        "Update a subscription — plan change (upgrade/downgrade), credit "
        "ceiling bump, or cycle change. Pro-rates from the effective-date. "
        "Used by the tenant-migration skill."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "space_id": {"type": "string"},
                "subscription_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "credit_ceiling_cents": {"type": "integer"},
                "billing_cycle": {"type": "string", "enum": ["monthly", "annual"]},
            },
            "required": ["space_id", "subscription_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        sid = kwargs.pop("space_id")
        sub = kwargs.pop("subscription_id")
        payload = {k: v for k, v in kwargs.items() if v is not None}
        try:
            status, body = await _request(
                "PATCH",
                f"/spaces/{sid}/subscriptions/{sub}",
                json_body=payload,
            )
            if not _ok(status):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"Updated subscription {sub}.",
                data={"subscription_id": sub, "changes": payload},
            )
        except Exception as e:
            logger.error("dhanam_subscription_update failed: %s", e)
            return ToolResult(success=False, error=str(e))


class DhanamCreditLedgerQueryTool(BaseTool):
    """Read the compute-credit ledger for a tenant."""

    name = "dhanam_credit_ledger_query"
    description = (
        "Return the compute-credit ledger for a space over a period. "
        "Surfaces remaining credit + burn rate so agents + tenant admins "
        "can see how much runway they have before hitting the ceiling."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "space_id": {"type": "string"},
                "period": {
                    "type": "string",
                    "enum": ["current", "month", "year"],
                    "default": "current",
                },
            },
            "required": ["space_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        sid = kwargs["space_id"]
        period = kwargs.get("period", "current")
        try:
            status, body = await _request(
                "GET", f"/spaces/{sid}/credits/ledger?period={period}"
            )
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"credits_used={body.get('used_cents')} / "
                    f"ceiling={body.get('ceiling_cents')}"
                ),
                data=body,
            )
        except Exception as e:
            logger.error("dhanam_credit_ledger_query failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_dhanam_provisioning_tools() -> list[BaseTool]:
    return [
        DhanamSpaceCreateTool(),
        DhanamSubscriptionCreateTool(),
        DhanamSubscriptionUpdateTool(),
        DhanamCreditLedgerQueryTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    DhanamSpaceCreateTool,
    DhanamSubscriptionCreateTool,
    DhanamSubscriptionUpdateTool,
):
    _cls.audience = Audience.PLATFORM
