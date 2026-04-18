"""Cloudflare R2 bucket + API-token management.

R2 buckets back tenant object storage across the ecosystem (subtext audio,
sim4d simulation cache, fortuna dataset parquet, …). Provisioning a bucket +
the S3-compatible credential to write to it needed a dashboard step on
2026-04-18 because no tool existed. This module closes that gap.

Two auth surfaces here:
- **Account-level token** (``CLOUDFLARE_API_TOKEN``) — for the bucket CRUD
  and R2 API-token issuance.
- **Per-bucket S3-compatible creds** — issued by the API-token tool and
  returned to the caller; never stored at rest.
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
    return "; ".join(e.get("message", str(e)) for e in errors) if errors else ""


# ---------------------------------------------------------------------------
# Bucket CRUD
# ---------------------------------------------------------------------------


class R2BucketListTool(BaseTool):
    """List R2 buckets in the account."""

    name = "r2_bucket_list"
    description = "List all R2 buckets in the MADFAM Cloudflare account."

    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        try:
            body = await _request("GET", f"accounts/{CF_ACCOUNT_ID}/r2/buckets")
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            buckets = (body.get("result") or {}).get("buckets") or []
            return ToolResult(
                success=True,
                output=f"Found {len(buckets)} bucket(s).",
                data={
                    "buckets": [
                        {
                            "name": b.get("name"),
                            "location": b.get("location"),
                            "created": b.get("creation_date"),
                        }
                        for b in buckets
                    ]
                },
            )
        except Exception as e:
            logger.error("r2_bucket_list failed: %s", e)
            return ToolResult(success=False, error=str(e))


class R2BucketCreateTool(BaseTool):
    """Create an R2 bucket."""

    name = "r2_bucket_create"
    description = (
        "Create an R2 bucket. 'location' defaults to auto (CF picks "
        "closest); set it explicitly to 'WNAM'/'ENAM'/'WEUR'/'EEUR'/'APAC' "
        "to pin the region. 'storage_class' defaults to 'Standard'; set to "
        "'InfrequentAccess' for warm-cache buckets."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Bucket name (globally unique within account).",
                },
                "location": {
                    "type": "string",
                    "enum": ["auto", "WNAM", "ENAM", "WEUR", "EEUR", "APAC"],
                    "default": "auto",
                },
                "storage_class": {
                    "type": "string",
                    "enum": ["Standard", "InfrequentAccess"],
                    "default": "Standard",
                },
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        name = kwargs["name"]
        payload: dict[str, Any] = {
            "name": name,
            "storageClass": kwargs.get("storage_class", "Standard"),
        }
        if kwargs.get("location") and kwargs["location"] != "auto":
            payload["locationHint"] = kwargs["location"]
        try:
            body = await _request(
                "POST",
                f"accounts/{CF_ACCOUNT_ID}/r2/buckets",
                json_body=payload,
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            result = body.get("result") or {}
            return ToolResult(
                success=True,
                output=f"Bucket created: {result.get('name')}.",
                data={
                    "name": result.get("name"),
                    "location": result.get("location"),
                    "endpoint": (
                        f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com/"
                        f"{result.get('name')}"
                    ),
                },
            )
        except Exception as e:
            logger.error("r2_bucket_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


class R2BucketDeleteTool(BaseTool):
    """Delete an R2 bucket. Bucket must be empty."""

    name = "r2_bucket_delete"
    description = (
        "Delete an R2 bucket. Must be empty (use the R2 dashboard or s3 "
        "delete-objects to empty it first). Irreversible — HITL-gated."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        name = kwargs["name"]
        try:
            body = await _request(
                "DELETE", f"accounts/{CF_ACCOUNT_ID}/r2/buckets/{name}"
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            return ToolResult(
                success=True, output=f"Deleted bucket {name}.", data={"name": name}
            )
        except Exception as e:
            logger.error("r2_bucket_delete failed: %s", e)
            return ToolResult(success=False, error=str(e))


# ---------------------------------------------------------------------------
# CORS (required for browser-side uploads, which sim4d studio does)
# ---------------------------------------------------------------------------


class R2CorsSetTool(BaseTool):
    """Set CORS rules on an R2 bucket."""

    name = "r2_cors_set"
    description = (
        "Configure CORS for an R2 bucket so browser apps can PUT/GET "
        "directly. Pass a list of CORS rules; each rule has "
        "allowed=[AllowedOrigin, AllowedMethod, AllowedHeader, "
        "ExposeHeader]. Rules replace any existing CORS config."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "rules": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of CORS rules.",
                },
            },
            "required": ["name", "rules"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        name = kwargs["name"]
        try:
            body = await _request(
                "PUT",
                f"accounts/{CF_ACCOUNT_ID}/r2/buckets/{name}/cors",
                json_body={"rules": kwargs["rules"]},
            )
            if not body.get("success"):
                return ToolResult(success=False, error=_fmt_err(body))
            return ToolResult(
                success=True,
                output=f"CORS set on {name}: {len(kwargs['rules'])} rule(s).",
                data={"name": name, "rules": len(kwargs["rules"])},
            )
        except Exception as e:
            logger.error("r2_cors_set failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_r2_tools() -> list[BaseTool]:
    return [
        R2BucketListTool(),
        R2BucketCreateTool(),
        R2BucketDeleteTool(),
        R2CorsSetTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    R2BucketListTool,
    R2BucketCreateTool,
    R2BucketDeleteTool,
    R2CorsSetTool,
):
    _cls.audience = Audience.PLATFORM
