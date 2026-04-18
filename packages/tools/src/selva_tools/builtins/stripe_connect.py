"""Stripe Connect provisioning — tenant-side payment collection.

Complements ``StripeWebhookCreateTool`` (which registers OUR account's
webhook endpoints). This module handles the tenant-side: Stripe Connect
Express accounts so tenants can collect payments directly, with Selva
as the platform and Dhanam as the revenue ledger.

Three tools:

- ``stripe_connect_account_create`` — create an Express connected
  account for the tenant. Returns account_id + onboarding url to surface
  to the tenant (they'll complete KYC on Stripe's hosted form).
- ``stripe_connect_account_link`` — regenerate an onboarding link for a
  tenant whose original expired (Stripe links are ~7 day TTL).
- ``stripe_connect_account_status`` — check charges_enabled /
  payouts_enabled flags. Returns the flags + requirements.currently_due
  so callers can surface exact gaps to the tenant.

Env: ``STRIPE_SECRET_KEY`` — the platform key, not a tenant key.

Auth model note: Stripe Connect accounts are CREATED by the platform key
and OWNED by the tenant (who completes KYC). Once fully onboarded, the
platform can initiate transfers on their behalf via destination charges
or direct charges; neither is performed by this module — those are
Dhanam billing-side tools.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
HTTP_TIMEOUT = 15.0


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        # Stripe uses form-encoded bodies, not JSON.
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _creds_check() -> str | None:
    if not STRIPE_SECRET_KEY:
        return "STRIPE_SECRET_KEY must be set."
    if not STRIPE_SECRET_KEY.startswith(("sk_live_", "sk_test_", "rk_live_", "rk_test_")):
        return (
            "STRIPE_SECRET_KEY looks malformed — expected sk_live_* / sk_test_* "
            "/ rk_live_* / rk_test_*."
        )
    return None


def _flatten(prefix: str, obj: Any, out: dict[str, str]) -> None:
    """Flatten a nested dict/list into Stripe's bracket form-encoding."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}[{k}]", v, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _flatten(f"{prefix}[{i}]", v, out)
    elif obj is None:
        return
    else:
        out[prefix] = str(obj)


def _form_encode(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in payload.items():
        _flatten(k, v, out)
    return out


async def _request(
    method: str, path: str, form: dict[str, Any] | None = None
):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.request(
            method,
            f"{STRIPE_API_BASE}{path}",
            headers=_headers(),
            data=_form_encode(form) if form else None,
        )
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text


def _ok(s: int) -> bool:
    return 200 <= s < 300


def _err(s: int, body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict):
            return err.get("message") or err.get("code") or str(err)
    return f"HTTP {s}: {body}"


class StripeConnectAccountCreateTool(BaseTool):
    """Create a Stripe Connect Express account for a tenant."""

    name = "stripe_connect_account_create"
    description = (
        "Create a Stripe Connect Express account on behalf of a tenant. "
        "Returns the account_id AND an onboarding_url the tenant must "
        "visit to complete KYC on Stripe's hosted form. The tenant owns "
        "the account; we're just the platform that provisioned it. Link "
        "TTL is ~7 days — use stripe_connect_account_link to refresh."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "ISO country code (e.g. 'MX' for Mexico, "
                    "'US' for USA). Determines compliance requirements.",
                    "default": "MX",
                },
                "email": {
                    "type": "string",
                    "description": "Primary contact email — Stripe sends "
                    "onboarding + compliance notices here.",
                },
                "business_type": {
                    "type": "string",
                    "enum": ["individual", "company", "non_profit", "government_entity"],
                },
                "return_url": {
                    "type": "string",
                    "description": "Where Stripe redirects after onboarding "
                    "finishes (success or refresh).",
                },
                "refresh_url": {
                    "type": "string",
                    "description": "Where Stripe redirects if the onboarding "
                    "link expires mid-flow.",
                },
                "metadata": {"type": "object"},
            },
            "required": ["email", "business_type", "return_url", "refresh_url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        country = kwargs.get("country", "MX")
        payload: dict[str, Any] = {
            "type": "express",
            "country": country,
            "email": kwargs["email"],
            "business_type": kwargs["business_type"],
            "capabilities": {
                "card_payments": {"requested": "true"},
                "transfers": {"requested": "true"},
            },
        }
        if kwargs.get("metadata"):
            payload["metadata"] = kwargs["metadata"]
        try:
            status, body = await _request("POST", "/accounts", form=payload)
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            account_id = body.get("id")
            # Now create the onboarding link.
            link_status, link_body = await _request(
                "POST",
                "/account_links",
                form={
                    "account": account_id,
                    "return_url": kwargs["return_url"],
                    "refresh_url": kwargs["refresh_url"],
                    "type": "account_onboarding",
                },
            )
            if not _ok(link_status) or not isinstance(link_body, dict):
                return ToolResult(
                    success=False,
                    error=(
                        f"account {account_id} created but link failed: "
                        f"{_err(link_status, link_body)}"
                    ),
                    data={"account_id": account_id},
                )
            return ToolResult(
                success=True,
                output=(
                    f"Connect account {account_id} created; onboarding "
                    f"URL valid until {link_body.get('expires_at')}"
                ),
                data={
                    "account_id": account_id,
                    "onboarding_url": link_body.get("url"),
                    "expires_at": link_body.get("expires_at"),
                    "country": country,
                },
            )
        except Exception as e:
            logger.error("stripe_connect_account_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


class StripeConnectAccountLinkTool(BaseTool):
    """Refresh an expired/expiring onboarding link."""

    name = "stripe_connect_account_link"
    description = (
        "Regenerate an onboarding link for an existing Connect account. "
        "Stripe onboarding links have ~7 day TTL; use this whenever a "
        "tenant says the original link expired or when resuming a "
        "partially-completed onboarding flow."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "return_url": {"type": "string"},
                "refresh_url": {"type": "string"},
                "link_type": {
                    "type": "string",
                    "enum": ["account_onboarding", "account_update"],
                    "default": "account_onboarding",
                },
            },
            "required": ["account_id", "return_url", "refresh_url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        payload = {
            "account": kwargs["account_id"],
            "return_url": kwargs["return_url"],
            "refresh_url": kwargs["refresh_url"],
            "type": kwargs.get("link_type", "account_onboarding"),
        }
        try:
            status, body = await _request("POST", "/account_links", form=payload)
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"New onboarding link for {kwargs['account_id']}",
                data={
                    "account_id": kwargs["account_id"],
                    "onboarding_url": body.get("url"),
                    "expires_at": body.get("expires_at"),
                },
            )
        except Exception as e:
            logger.error("stripe_connect_account_link failed: %s", e)
            return ToolResult(success=False, error=str(e))


class StripeConnectAccountStatusTool(BaseTool):
    """Read charges_enabled + payouts_enabled + outstanding requirements."""

    name = "stripe_connect_account_status"
    description = (
        "Check a Connect account's onboarding state. Returns "
        "charges_enabled, payouts_enabled, and requirements.currently_due "
        "(the exact fields Stripe still needs from the tenant). Use to "
        "decide whether a tenant can receive payments yet, and to surface "
        "exact onboarding gaps rather than a generic 'incomplete' error."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"account_id": {"type": "string"}},
            "required": ["account_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        aid = kwargs["account_id"]
        try:
            status, body = await _request("GET", f"/accounts/{aid}")
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            requirements = body.get("requirements") or {}
            return ToolResult(
                success=True,
                output=(
                    f"{aid}: charges={body.get('charges_enabled')} "
                    f"payouts={body.get('payouts_enabled')} "
                    f"due={len(requirements.get('currently_due') or [])}"
                ),
                data={
                    "account_id": aid,
                    "charges_enabled": body.get("charges_enabled"),
                    "payouts_enabled": body.get("payouts_enabled"),
                    "details_submitted": body.get("details_submitted"),
                    "currently_due": requirements.get("currently_due") or [],
                    "past_due": requirements.get("past_due") or [],
                    "disabled_reason": requirements.get("disabled_reason"),
                },
            )
        except Exception as e:
            logger.error("stripe_connect_account_status failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_stripe_connect_tools() -> list[BaseTool]:
    return [
        StripeConnectAccountCreateTool(),
        StripeConnectAccountLinkTool(),
        StripeConnectAccountStatusTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    StripeConnectAccountCreateTool,
    StripeConnectAccountLinkTool,
    StripeConnectAccountStatusTool,
):
    _cls.audience = Audience.PLATFORM
