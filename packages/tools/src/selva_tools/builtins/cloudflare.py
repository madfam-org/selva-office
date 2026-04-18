"""Cloudflare management tools for the Selva Swarm.

Covers zone creation, DNS record CRUD, Page Rules (for redirects), and the
composite NS-migration flow that moves a domain from Porkbun nameservers
to Cloudflare nameservers with a functioning redirect on the other side.

API Docs: https://developers.cloudflare.com/api/
Auth: Requires ``CLOUDFLARE_API_TOKEN`` and ``CLOUDFLARE_ACCOUNT_ID``.

Token scopes needed:
- ``Zone:Edit`` (create zones + page rules)
- ``DNS:Edit`` (create records)

Page Rules (legacy) API is used for redirects because the Rulesets API
``http_request_dynamic_redirect`` phase requires a stricter token scope
(``Zone Rulesets:Edit``) that isn't provisioned on the shared
``cloudflare-api-credentials`` secret. Page Rules cover the same use
case for full-zone 301 redirects.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CF_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {CF_TOKEN}",
        "Content-Type": "application/json",
    }


def _check_credentials() -> str | None:
    if not CF_TOKEN:
        return "CLOUDFLARE_API_TOKEN must be set."
    if not CF_ACCOUNT_ID:
        return "CLOUDFLARE_ACCOUNT_ID must be set."
    return None


async def _request(
    method: str, path: str, json: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Make a request to the Cloudflare API and return the parsed body."""
    url = f"{CF_API_BASE}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method, url, headers=_auth_headers(), json=json
        )
        return resp.json()


def _fmt_errors(body: dict[str, Any]) -> str:
    errors = body.get("errors") or []
    if not errors:
        return ""
    return "; ".join(e.get("message", str(e)) for e in errors)


# ---------------------------------------------------------------------------
# Zone management
# ---------------------------------------------------------------------------


class CloudflareCreateZoneTool(BaseTool):
    """Create a new zone under the configured CF account. Returns zone id + NS."""

    name = "cloudflare_create_zone"
    description = (
        "Create a new DNS zone in the MADFAM Cloudflare account. Returns the "
        "zone id and the two nameservers CF assigned — use those to update "
        "the registrar's NS records so traffic starts flowing through CF."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Apex domain (e.g. 'example.com').",
                },
                "type": {
                    "type": "string",
                    "enum": ["full", "partial"],
                    "default": "full",
                    "description": "'full' = CF is the authoritative DNS "
                    "(standard setup); 'partial' = CF-for-SaaS CNAME setup.",
                },
            },
            "required": ["domain"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _check_credentials()
        if err:
            return ToolResult(success=False, error=err)
        domain = kwargs["domain"]
        zone_type = kwargs.get("type", "full")
        try:
            body = await _request(
                "POST",
                "zones",
                json={
                    "name": domain,
                    "account": {"id": CF_ACCOUNT_ID},
                    "type": zone_type,
                },
            )
            if not body.get("success"):
                return ToolResult(
                    success=False, error=f"cloudflare: {_fmt_errors(body)}"
                )
            result = body.get("result") or {}
            ns = result.get("name_servers") or []
            return ToolResult(
                success=True,
                output=(
                    f"Zone created: {domain} ({result.get('id')}). "
                    f"Assigned NS: {', '.join(ns)}"
                ),
                data={
                    "zone_id": result.get("id"),
                    "name": result.get("name"),
                    "status": result.get("status"),
                    "name_servers": ns,
                },
            )
        except Exception as e:
            logger.error("cloudflare_create_zone failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CloudflareListZonesTool(BaseTool):
    """List zones in the CF account, optionally filtered by name."""

    name = "cloudflare_list_zones"
    description = (
        "List zones in the MADFAM Cloudflare account. Optional 'name' filter "
        "returns exactly one zone if it exists — useful to check whether a "
        "domain is already onboarded to CF."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Apex domain filter (optional).",
                },
                "per_page": {
                    "type": "integer",
                    "default": 50,
                    "description": "Page size (max 50).",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _check_credentials()
        if err:
            return ToolResult(success=False, error=err)
        params: list[str] = [f"per_page={kwargs.get('per_page', 50)}"]
        if kwargs.get("name"):
            params.append(f"name={kwargs['name']}")
        path = "zones?" + "&".join(params)
        try:
            body = await _request("GET", path)
            if not body.get("success"):
                return ToolResult(
                    success=False, error=f"cloudflare: {_fmt_errors(body)}"
                )
            zones = body.get("result") or []
            summary = [
                {
                    "name": z.get("name"),
                    "id": z.get("id"),
                    "status": z.get("status"),
                    "name_servers": z.get("name_servers"),
                }
                for z in zones
            ]
            return ToolResult(
                success=True,
                output=f"Found {len(zones)} zone(s).",
                data={"zones": summary},
            )
        except Exception as e:
            logger.error("cloudflare_list_zones failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# DNS records
# ---------------------------------------------------------------------------


class CloudflareCreateDnsRecordTool(BaseTool):
    """Create a DNS record inside a CF zone."""

    name = "cloudflare_create_dns_record"
    description = (
        "Create a DNS record in a Cloudflare zone. Supports A/AAAA/CNAME/TXT "
        "and proxied/unproxied records. 'proxied=true' is required for any "
        "domain that needs Page Rules / Redirect Rules / WAF to fire."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "zone_id": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["A", "AAAA", "CNAME", "TXT", "MX", "NS"],
                },
                "name": {
                    "type": "string",
                    "description": "Record name (e.g. 'www' or '@' for apex "
                    "or '*' for wildcard).",
                },
                "content": {"type": "string", "description": "Record value."},
                "proxied": {
                    "type": "boolean",
                    "default": True,
                    "description": "True = traffic goes through CF proxy "
                    "(required for Page Rules to fire).",
                },
                "ttl": {"type": "integer", "default": 1, "description": "1 = auto."},
                "priority": {
                    "type": "integer",
                    "description": "MX priority (only for MX records).",
                },
            },
            "required": ["zone_id", "type", "name", "content"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _check_credentials()
        if err:
            return ToolResult(success=False, error=err)
        zone_id = kwargs["zone_id"]
        payload: dict[str, Any] = {
            "type": kwargs["type"],
            "name": kwargs["name"],
            "content": kwargs["content"],
            "ttl": kwargs.get("ttl", 1),
            "proxied": kwargs.get("proxied", True),
        }
        if kwargs.get("priority") is not None:
            payload["priority"] = kwargs["priority"]
        try:
            body = await _request(
                "POST", f"zones/{zone_id}/dns_records", json=payload
            )
            if not body.get("success"):
                return ToolResult(
                    success=False, error=f"cloudflare: {_fmt_errors(body)}"
                )
            result = body.get("result") or {}
            return ToolResult(
                success=True,
                output=(
                    f"Record created: {result.get('type')} {result.get('name')}"
                    f" → {result.get('content')}"
                ),
                data={
                    "record_id": result.get("id"),
                    "name": result.get("name"),
                    "type": result.get("type"),
                    "content": result.get("content"),
                    "proxied": result.get("proxied"),
                },
            )
        except Exception as e:
            logger.error("cloudflare_create_dns_record failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CloudflareListDnsRecordsTool(BaseTool):
    """List DNS records in a CF zone."""

    name = "cloudflare_list_dns_records"
    description = "List all DNS records in a Cloudflare zone."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"zone_id": {"type": "string"}},
            "required": ["zone_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _check_credentials()
        if err:
            return ToolResult(success=False, error=err)
        zone_id = kwargs["zone_id"]
        try:
            body = await _request("GET", f"zones/{zone_id}/dns_records?per_page=100")
            if not body.get("success"):
                return ToolResult(
                    success=False, error=f"cloudflare: {_fmt_errors(body)}"
                )
            records = body.get("result") or []
            return ToolResult(
                success=True,
                output=f"Found {len(records)} record(s).",
                data={
                    "records": [
                        {
                            "id": r.get("id"),
                            "type": r.get("type"),
                            "name": r.get("name"),
                            "content": r.get("content"),
                            "proxied": r.get("proxied"),
                        }
                        for r in records
                    ]
                },
            )
        except Exception as e:
            logger.error("cloudflare_list_dns_records failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Page Rules (legacy, used for full-domain redirects)
# ---------------------------------------------------------------------------


class CloudflareCreateRedirectRuleTool(BaseTool):
    """Create a full-domain 301 redirect via a CF Page Rule.

    Targets ``*<domain>/*`` so apex AND all subdomains AND every path
    forward to ``<target>/$2``, preserving path + query string.
    """

    name = "cloudflare_create_redirect_rule"
    description = (
        "Create a Cloudflare Page Rule that 301-redirects a full domain "
        "(including subdomains and paths) to a target URL. Uses the "
        "'forwarding_url' action with a wildcard match. Requires a "
        "proxied A record on '@' and '*' in the zone (Page Rules only fire "
        "for proxied traffic)."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "zone_id": {"type": "string"},
                "domain": {
                    "type": "string",
                    "description": "Source domain (apex, e.g. 'old.example').",
                },
                "target": {
                    "type": "string",
                    "description": "Destination URL without trailing slash "
                    "(e.g. 'https://new.example').",
                },
                "status_code": {
                    "type": "integer",
                    "enum": [301, 302],
                    "default": 301,
                },
            },
            "required": ["zone_id", "domain", "target"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _check_credentials()
        if err:
            return ToolResult(success=False, error=err)
        zone_id = kwargs["zone_id"]
        domain = kwargs["domain"]
        target = kwargs["target"].rstrip("/")
        status = kwargs.get("status_code", 301)
        payload = {
            "targets": [
                {
                    "target": "url",
                    "constraint": {
                        "operator": "matches",
                        "value": f"*{domain}/*",
                    },
                }
            ],
            "actions": [
                {
                    "id": "forwarding_url",
                    "value": {"url": f"{target}/$2", "status_code": status},
                }
            ],
            "priority": 1,
            "status": "active",
        }
        try:
            body = await _request(
                "POST", f"zones/{zone_id}/pagerules", json=payload
            )
            if not body.get("success"):
                return ToolResult(
                    success=False, error=f"cloudflare: {_fmt_errors(body)}"
                )
            result = body.get("result") or {}
            return ToolResult(
                success=True,
                output=(
                    f"Page Rule created: *{domain}/* → {target}/$2 "
                    f"({status})"
                ),
                data={
                    "rule_id": result.get("id"),
                    "priority": result.get("priority"),
                    "status": result.get("status"),
                },
            )
        except Exception as e:
            logger.error("cloudflare_create_redirect_rule failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CloudflareListPageRulesTool(BaseTool):
    """List existing Page Rules in a zone."""

    name = "cloudflare_list_page_rules"
    description = "List all Page Rules in a Cloudflare zone."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"zone_id": {"type": "string"}},
            "required": ["zone_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _check_credentials()
        if err:
            return ToolResult(success=False, error=err)
        zone_id = kwargs["zone_id"]
        try:
            body = await _request("GET", f"zones/{zone_id}/pagerules")
            if not body.get("success"):
                return ToolResult(
                    success=False, error=f"cloudflare: {_fmt_errors(body)}"
                )
            rules = body.get("result") or []
            return ToolResult(
                success=True,
                output=f"Found {len(rules)} Page Rule(s).",
                data={"rules": rules},
            )
        except Exception as e:
            logger.error("cloudflare_list_page_rules failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Registry helper
# ---------------------------------------------------------------------------


def get_cloudflare_tools() -> list[BaseTool]:
    """Return all Cloudflare tools for registration in the tool registry."""
    return [
        CloudflareCreateZoneTool(),
        CloudflareListZonesTool(),
        CloudflareCreateDnsRecordTool(),
        CloudflareListDnsRecordsTool(),
        CloudflareCreateRedirectRuleTool(),
        CloudflareListPageRulesTool(),
    ]
