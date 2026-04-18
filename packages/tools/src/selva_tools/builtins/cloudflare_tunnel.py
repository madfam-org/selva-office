"""Cloudflare Zero Trust Tunnel management.

Every new service we ship on the cluster needs a tunnel route that maps a
public hostname to an in-cluster ClusterIP service. Without a Tunnel tool the
operator has to hand-edit the cloudflared ConfigMap / use the CF dashboard.
This module lets an agent do it end-to-end.

The CF API surface here is the Account-level Tunnel v2 (cfd_tunnel) API.
Token scopes required: ``Account: Cloudflare Tunnel: Edit`` plus
``Zone: DNS: Edit`` for the CNAME that points the hostname at the tunnel's
``<uuid>.cfargotunnel.com``.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CF_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {CF_TOKEN}",
        "Content-Type": "application/json",
    }


def _creds_check() -> str | None:
    if not CF_TOKEN:
        return "CLOUDFLARE_API_TOKEN must be set."
    if not CF_ACCOUNT_ID:
        return "CLOUDFLARE_ACCOUNT_ID must be set."
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
    if not errors:
        return ""
    return "; ".join(e.get("message", str(e)) for e in errors)


# ---------------------------------------------------------------------------
# Tunnel CRUD
# ---------------------------------------------------------------------------


class CfTunnelListTool(BaseTool):
    """List Cloudflare Tunnels in the account."""

    name = "cf_tunnel_list"
    description = (
        "List Cloudflare Zero Trust tunnels. Useful for discovering the "
        "tunnel id of the cluster's cloudflared deployment before routing "
        "a new hostname through it."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string"},
                "is_deleted": {"type": "boolean", "default": False},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        params: list[str] = []
        if kwargs.get("is_deleted") is False:
            params.append("is_deleted=false")
        if kwargs.get("name_contains"):
            params.append(f"name={kwargs['name_contains']}")
        qs = "?" + "&".join(params) if params else ""
        try:
            body = await _request(
                "GET", f"accounts/{CF_ACCOUNT_ID}/cfd_tunnel{qs}"
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            tunnels = body.get("result") or []
            return ToolResult(
                success=True,
                output=f"Found {len(tunnels)} tunnel(s).",
                data={
                    "tunnels": [
                        {
                            "id": t.get("id"),
                            "name": t.get("name"),
                            "status": t.get("status"),
                            "connections": len(t.get("connections") or []),
                        }
                        for t in tunnels
                    ]
                },
            )
        except Exception as e:
            logger.error("cf_tunnel_list failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CfTunnelCreateTool(BaseTool):
    """Create a new Tunnel. Returns the tunnel id + secret for cloudflared config."""

    name = "cf_tunnel_create"
    description = (
        "Create a new Cloudflare Zero Trust Tunnel. The returned "
        "tunnel_secret must be planted in the cloudflared pod's credentials "
        "secret (base64-encoded JSON with AccountTag/TunnelID/TunnelSecret) "
        "before the tunnel can establish. Keep tunnel_secret out of logs."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable tunnel name, e.g. 'madfam-foundry'.",
                },
                "tunnel_secret": {
                    "type": "string",
                    "description": "Optional base64-encoded 32-byte secret. "
                    "If omitted, a fresh one is generated.",
                },
                "config_src": {
                    "type": "string",
                    "enum": ["cloudflare", "local"],
                    "default": "cloudflare",
                    "description": "'cloudflare' uses remotely-managed "
                    "config (Zero Trust dashboard); 'local' uses a config.yml "
                    "bundled with the cloudflared pod.",
                },
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        import base64
        sec = kwargs.get("tunnel_secret")
        if not sec:
            sec = base64.b64encode(secrets.token_bytes(32)).decode()
        payload = {
            "name": kwargs["name"],
            "tunnel_secret": sec,
            "config_src": kwargs.get("config_src", "cloudflare"),
        }
        try:
            body = await _request(
                "POST", f"accounts/{CF_ACCOUNT_ID}/cfd_tunnel", json_body=payload
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            result = body.get("result") or {}
            return ToolResult(
                success=True,
                output=(
                    f"Tunnel created: {result.get('name')} ({result.get('id')})."
                ),
                data={
                    "tunnel_id": result.get("id"),
                    "name": result.get("name"),
                    "tunnel_secret": sec,
                    "cname_target": f"{result.get('id')}.cfargotunnel.com",
                },
            )
        except Exception as e:
            logger.error("cf_tunnel_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# Ingress config (routes public hostnames to origin services)
# ---------------------------------------------------------------------------


class CfTunnelGetIngressTool(BaseTool):
    """Read the current ingress rules for a tunnel (cloudflare-managed config)."""

    name = "cf_tunnel_get_ingress"
    description = (
        "Read the current ingress rule list for a tunnel managed via "
        "cloudflare-side config. The list is ordered; the first matching "
        "rule wins. Always ends with a catch-all (usually http_status:404)."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"tunnel_id": {"type": "string"}},
            "required": ["tunnel_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        tid = kwargs["tunnel_id"]
        try:
            body = await _request(
                "GET", f"accounts/{CF_ACCOUNT_ID}/cfd_tunnel/{tid}/configurations"
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            config = (body.get("result") or {}).get("config") or {}
            return ToolResult(
                success=True,
                output=f"{len(config.get('ingress') or [])} ingress rule(s).",
                data={"config": config},
            )
        except Exception as e:
            logger.error("cf_tunnel_get_ingress failed: %s", e)
            return ToolResult(success=False, error=str(e))


class CfTunnelPutIngressTool(BaseTool):
    """Replace the full ingress rule list (cloudflare-managed config)."""

    name = "cf_tunnel_put_ingress"
    description = (
        "Replace the ingress rule list for a tunnel. PUT semantics — the "
        "full list must include the catch-all at the end. Use "
        "cf_tunnel_get_ingress first, append your new rule BEFORE the "
        "catch-all, then PUT the combined list."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tunnel_id": {"type": "string"},
                "ingress": {
                    "type": "array",
                    "description": "Ordered list; each item is "
                    "{hostname, service, path?, originRequest?}. Final item "
                    "must be a catch-all with no hostname and "
                    "service='http_status:404'.",
                    "items": {"type": "object"},
                },
            },
            "required": ["tunnel_id", "ingress"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        tid = kwargs["tunnel_id"]
        ingress = kwargs["ingress"]
        # Validate catch-all at the end.
        if not ingress or ingress[-1].get("hostname"):
            return ToolResult(
                success=False,
                error="ingress list must end with a hostname-less catch-all rule",
            )
        try:
            body = await _request(
                "PUT",
                f"accounts/{CF_ACCOUNT_ID}/cfd_tunnel/{tid}/configurations",
                json_body={"config": {"ingress": ingress}},
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            return ToolResult(
                success=True,
                output=f"Updated ingress on tunnel {tid}: {len(ingress)} rule(s).",
                data={"rules": len(ingress)},
            )
        except Exception as e:
            logger.error("cf_tunnel_put_ingress failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_cloudflare_tunnel_tools() -> list[BaseTool]:
    return [
        CfTunnelListTool(),
        CfTunnelCreateTool(),
        CfTunnelGetIngressTool(),
        CfTunnelPutIngressTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    CfTunnelListTool,
    CfTunnelCreateTool,
    CfTunnelGetIngressTool,
    CfTunnelPutIngressTool,
):
    _cls.audience = Audience.PLATFORM
