"""Resend domain provisioning — add, verify, list, delete.

Complements existing ``resend_webhook_create``. When a new tenant wants to
send from their own domain (rather than our shared ``@selva.town``), we add
it to Resend, surface the SPF/DKIM/DMARC records for the tenant to publish
on their DNS, and poll verification status.

Env: ``RESEND_API_KEY`` — the full-access key documented in org-config.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

RESEND_API_BASE = "https://api.resend.com"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }


def _creds_check() -> str | None:
    if not RESEND_API_KEY:
        return "RESEND_API_KEY must be set."
    return None


async def _request(method: str, path: str, json_body: dict[str, Any] | None = None):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method,
            f"{RESEND_API_BASE}{path}",
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
        return body.get("message") or body.get("error") or str(body)
    return f"HTTP {s}: {body}"


class ResendDomainAddTool(BaseTool):
    """Add a domain to Resend and surface the required DNS records."""

    name = "resend_domain_add"
    description = (
        "Register a sending domain with Resend. The returned 'records' list "
        "is the full set of DNS records (SPF TXT, DKIM CNAME, optional DMARC) "
        "the tenant must publish on their domain before Resend will start "
        "accepting sends. Surface these verbatim to the tenant's DNS admin."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Domain name (e.g. 'tenant.com').",
                },
                "region": {
                    "type": "string",
                    "enum": ["us-east-1", "eu-west-1", "sa-east-1", "ap-northeast-1"],
                    "default": "us-east-1",
                },
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        payload = {
            "name": kwargs["name"],
            "region": kwargs.get("region", "us-east-1"),
        }
        try:
            status, body = await _request("POST", "/domains", json_body=payload)
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Domain added: {body.get('name')} "
                    f"({body.get('id')}). {len(body.get('records') or [])} "
                    f"DNS record(s) to publish."
                ),
                data={
                    "domain_id": body.get("id"),
                    "name": body.get("name"),
                    "status": body.get("status"),
                    "records": body.get("records") or [],
                },
            )
        except Exception as e:
            logger.error("resend_domain_add failed: %s", e)
            return ToolResult(success=False, error=str(e))


class ResendDomainVerifyTool(BaseTool):
    """Trigger Resend to re-verify a domain's DNS records."""

    name = "resend_domain_verify"
    description = (
        "Ask Resend to re-check the DNS records for a domain. Resend polls "
        "automatically, but calling this shortens the feedback loop. Returns "
        "the current status ('pending' / 'verified' / 'failed')."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"domain_id": {"type": "string"}},
            "required": ["domain_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        did = kwargs["domain_id"]
        try:
            status, body = await _request("POST", f"/domains/{did}/verify")
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"Verify triggered on {did}; status: {body.get('status')}",
                data={
                    "domain_id": did,
                    "status": body.get("status"),
                },
            )
        except Exception as e:
            logger.error("resend_domain_verify failed: %s", e)
            return ToolResult(success=False, error=str(e))


class ResendDomainListTool(BaseTool):
    """List domains registered in the Resend account."""

    name = "resend_domain_list"
    description = "List all Resend domains with their current verification status."

    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        try:
            status, body = await _request("GET", "/domains")
            if not _ok(status):
                return ToolResult(success=False, error=_err(status, body))
            items = body.get("data") if isinstance(body, dict) else []
            return ToolResult(
                success=True,
                output=f"Found {len(items or [])} domain(s).",
                data={
                    "domains": [
                        {
                            "id": d.get("id"),
                            "name": d.get("name"),
                            "status": d.get("status"),
                            "region": d.get("region"),
                        }
                        for d in (items or [])
                    ]
                },
            )
        except Exception as e:
            logger.error("resend_domain_list failed: %s", e)
            return ToolResult(success=False, error=str(e))


class ResendDomainDeleteTool(BaseTool):
    """Delete a domain. Irreversible."""

    name = "resend_domain_delete"
    description = (
        "Remove a domain from Resend. Immediately stops sending via that "
        "domain. Use as part of tenant offboarding; HITL-gate."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"domain_id": {"type": "string"}},
            "required": ["domain_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        did = kwargs["domain_id"]
        try:
            status, body = await _request("DELETE", f"/domains/{did}")
            if not _ok(status):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True, output=f"Deleted domain {did}.", data={"domain_id": did}
            )
        except Exception as e:
            logger.error("resend_domain_delete failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_resend_domain_tools() -> list[BaseTool]:
    return [
        ResendDomainAddTool(),
        ResendDomainVerifyTool(),
        ResendDomainListTool(),
        ResendDomainDeleteTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    ResendDomainAddTool,
    ResendDomainVerifyTool,
    ResendDomainListTool,
    ResendDomainDeleteTool,
):
    _cls.audience = Audience.PLATFORM
