"""Cloudflare for SaaS custom-hostname CRUD.

Tenants that bring their own domain (``tenant.com`` → ``tenant.selva.town``)
need a Custom Hostname record on our fallback-origin zone. This module
surfaces the 4 endpoints required to add, verify, read, and delete those.

The fallback-origin concept: we designate one of our owned zones (typically
``selva.town``) as the fallback. Every Custom Hostname proxies its traffic
there. Inside the zone, a catch-all hostname-based Cloudflare Tunnel route
maps incoming requests to the right in-cluster service.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {CF_TOKEN}",
        "Content-Type": "application/json",
    }


def _creds_check() -> str | None:
    if not CF_TOKEN:
        return "CLOUDFLARE_API_TOKEN must be set."
    return None


async def _request(
    method: str, path: str, json_body: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method, f"{CF_API_BASE}/{path}", headers=_headers(), json=json_body
        )
        return resp.json()


def _fmt_err(body: dict[str, Any]) -> str:
    errors = body.get("errors") or []
    return "; ".join(e.get("message", str(e)) for e in errors) if errors else ""


class CfSaasHostnameAddTool(BaseTool):
    """Add a custom hostname to the fallback-origin zone."""

    name = "cf_saas_hostname_add"
    description = (
        "Register a tenant's custom domain with Cloudflare for SaaS. The "
        "returned 'ownership_verification' value must be planted as a DNS "
        "TXT record on the tenant's domain before CF starts proxying the "
        "hostname. SSL validation is via 'http' (CF places a file at "
        "/.well-known/acme-challenge) or 'txt' (TXT record on _acme-challenge)."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Zone id of the fallback-origin zone "
                    "(typically selva.town).",
                },
                "hostname": {
                    "type": "string",
                    "description": "The tenant's custom hostname (e.g. "
                    "'app.tenant.com').",
                },
                "ssl_method": {
                    "type": "string",
                    "enum": ["http", "txt"],
                    "default": "http",
                },
                "custom_origin_server": {
                    "type": "string",
                    "description": "Optional override for the origin this "
                    "hostname resolves to. Omit to use the zone's "
                    "fallback-origin.",
                },
            },
            "required": ["zone_id", "hostname"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        zid = kwargs["zone_id"]
        payload: dict[str, Any] = {
            "hostname": kwargs["hostname"],
            "ssl": {
                "method": kwargs.get("ssl_method", "http"),
                "type": "dv",
            },
        }
        if kwargs.get("custom_origin_server"):
            payload["custom_origin_server"] = kwargs["custom_origin_server"]
        try:
            body = await _request(
                "POST",
                f"zones/{zid}/custom_hostnames",
                json_body=payload,
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            r = body.get("result") or {}
            ov = r.get("ownership_verification") or {}
            return ToolResult(
                success=True,
                output=(
                    f"Custom hostname queued: {r.get('hostname')}. "
                    f"Status: {r.get('status')}."
                ),
                data={
                    "hostname_id": r.get("id"),
                    "hostname": r.get("hostname"),
                    "status": r.get("status"),
                    "ssl_status": (r.get("ssl") or {}).get("status"),
                    "ownership_verification": {
                        "type": ov.get("type"),
                        "name": ov.get("name"),
                        "value": ov.get("value"),
                    },
                },
            )
        except Exception as e:
            logger.error("cf_saas_hostname_add failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CfSaasHostnameStatusTool(BaseTool):
    """Read the current status of a custom hostname."""

    name = "cf_saas_hostname_status"
    description = (
        "Poll the validation + SSL state of a custom hostname. Statuses: "
        "'pending' (awaiting ownership verification), 'active' (serving), "
        "'moved' / 'deleted' (removed), 'blocked'."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "zone_id": {"type": "string"},
                "hostname_id": {"type": "string"},
            },
            "required": ["zone_id", "hostname_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        zid = kwargs["zone_id"]
        hid = kwargs["hostname_id"]
        try:
            body = await _request("GET", f"zones/{zid}/custom_hostnames/{hid}")
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            r = body.get("result") or {}
            return ToolResult(
                success=True,
                output=(
                    f"{r.get('hostname')}: {r.get('status')} "
                    f"(ssl: {(r.get('ssl') or {}).get('status')})"
                ),
                data={
                    "hostname": r.get("hostname"),
                    "status": r.get("status"),
                    "ssl": r.get("ssl"),
                    "ownership_verification": r.get("ownership_verification"),
                },
            )
        except Exception as e:
            logger.error("cf_saas_hostname_status failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CfSaasHostnameListTool(BaseTool):
    """List custom hostnames on a zone."""

    name = "cf_saas_hostname_list"
    description = "List all Cloudflare-for-SaaS custom hostnames on a zone."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "zone_id": {"type": "string"},
                "hostname_contains": {"type": "string"},
            },
            "required": ["zone_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        zid = kwargs["zone_id"]
        qs = ""
        if kwargs.get("hostname_contains"):
            qs = f"?hostname={kwargs['hostname_contains']}"
        try:
            body = await _request("GET", f"zones/{zid}/custom_hostnames{qs}")
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            items = body.get("result") or []
            return ToolResult(
                success=True,
                output=f"Found {len(items)} hostname(s).",
                data={
                    "hostnames": [
                        {
                            "id": h.get("id"),
                            "hostname": h.get("hostname"),
                            "status": h.get("status"),
                        }
                        for h in items
                    ]
                },
            )
        except Exception as e:
            logger.error("cf_saas_hostname_list failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CfSaasHostnameDeleteTool(BaseTool):
    """Delete a custom hostname."""

    name = "cf_saas_hostname_delete"
    description = (
        "Remove a custom hostname from the fallback-origin zone. Tenant's "
        "domain stops resolving via CF immediately."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "zone_id": {"type": "string"},
                "hostname_id": {"type": "string"},
            },
            "required": ["zone_id", "hostname_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        zid = kwargs["zone_id"]
        hid = kwargs["hostname_id"]
        try:
            body = await _request(
                "DELETE", f"zones/{zid}/custom_hostnames/{hid}"
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            return ToolResult(
                success=True,
                output=f"Deleted custom hostname {hid}.",
                data={"hostname_id": hid},
            )
        except Exception as e:
            logger.error("cf_saas_hostname_delete failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_cloudflare_saas_tools() -> list[BaseTool]:
    return [
        CfSaasHostnameAddTool(),
        CfSaasHostnameStatusTool(),
        CfSaasHostnameListTool(),
        CfSaasHostnameDeleteTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    CfSaasHostnameAddTool,
    CfSaasHostnameStatusTool,
    CfSaasHostnameListTool,
    CfSaasHostnameDeleteTool,
):
    _cls.audience = Audience.PLATFORM
