"""Karafiel org + SAT cert provisioning.

Karafiel is the MADFAM compliance engine for Mexican fiscal operations. Every
tenant that will invoice inside Mexico needs:
- A Karafiel ``org`` record (RFC + razón social + régimen fiscal)
- Their SAT .cer/.key certificates uploaded
- PAC registration for CFDI 4.0 stamping

This module exposes those bootstrap steps as tools. SAT cert upload is
explicitly HITL-gated because the private key is a signing artifact of the
tenant's Mexican legal entity — there's no agent justification for a cert
upload without a legal representative signing off.

Env: ``KARAFIEL_API_URL`` (default ``https://api.karafiel.mx``),
``KARAFIEL_ADMIN_TOKEN``.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

KARAFIEL_API_URL = os.environ.get("KARAFIEL_API_URL", "https://api.karafiel.mx")
KARAFIEL_ADMIN_TOKEN = os.environ.get("KARAFIEL_ADMIN_TOKEN", "")


def _headers(json_content: bool = True) -> dict[str, str]:
    h = {"Authorization": f"Bearer {KARAFIEL_ADMIN_TOKEN}"}
    if json_content:
        h["Content-Type"] = "application/json"
    return h


def _creds_check() -> str | None:
    if not KARAFIEL_ADMIN_TOKEN:
        return "KARAFIEL_ADMIN_TOKEN must be set."
    return None


async def _request(
    method: str, path: str, json_body: dict[str, Any] | None = None
):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method,
            f"{KARAFIEL_API_URL.rstrip('/')}{path}",
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


class KarafielOrgCreateTool(BaseTool):
    """Create a Karafiel org (the Mexican legal-entity record)."""

    name = "karafiel_org_create"
    description = (
        "Create a Karafiel organization — the fiscal entity record for a "
        "tenant operating in Mexico. Requires RFC (validated against SAT "
        "format), razón social, régimen fiscal code (see SAT catálogo), and "
        "domicilio fiscal (5-digit CP). Does NOT upload the SAT certs — "
        "that's a separate, HITL-gated step."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rfc": {
                    "type": "string",
                    "description": "12-13 character RFC (moral or física).",
                },
                "razon_social": {
                    "type": "string",
                    "description": "Exact legal name as registered with SAT.",
                },
                "regimen_fiscal": {
                    "type": "string",
                    "description": "SAT régimen fiscal code (e.g. '601' for "
                    "General de Ley Personas Morales).",
                },
                "domicilio_fiscal_cp": {
                    "type": "string",
                    "description": "5-digit postal code of the tax domicile.",
                },
                "correo_contacto": {"type": "string"},
            },
            "required": [
                "rfc",
                "razon_social",
                "regimen_fiscal",
                "domicilio_fiscal_cp",
            ],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        payload = {
            "rfc": kwargs["rfc"],
            "razon_social": kwargs["razon_social"],
            "regimen_fiscal": kwargs["regimen_fiscal"],
            "domicilio_fiscal_cp": kwargs["domicilio_fiscal_cp"],
            "correo_contacto": kwargs.get("correo_contacto", ""),
        }
        try:
            status, body = await _request("POST", "/api/v1/orgs", json_body=payload)
            if not _ok(status) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"Karafiel org created: {body.get('rfc')} ({body.get('id')}).",
                data={
                    "org_id": body.get("id"),
                    "rfc": body.get("rfc"),
                    "sat_cert_uploaded": False,
                    "pac_registered": False,
                },
            )
        except Exception as e:
            logger.error("karafiel_org_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


class KarafielSatCertUploadTool(BaseTool):
    """Upload SAT .cer + .key for a Karafiel org. HITL-gated."""

    name = "karafiel_sat_cert_upload"
    description = (
        "Upload the SAT .cer + .key + key password for a Karafiel org. This "
        "is the CFDI signing artifact for the tenant's legal entity — treat "
        "the key bytes as a strict secret and never log them. Files are "
        "base64-encoded for transport. ALWAYS HITL-gated: a legal "
        "representative of the tenant must sign off before the swarm "
        "uploads a cert."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "cer_base64": {
                    "type": "string",
                    "description": "Base64-encoded .cer file (public).",
                },
                "key_base64": {
                    "type": "string",
                    "description": "Base64-encoded .key file (private — PFX/PKCS8).",
                },
                "key_password": {
                    "type": "string",
                    "description": "Password to decrypt .key at runtime.",
                },
            },
            "required": ["org_id", "cer_base64", "key_base64", "key_password"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        oid = kwargs["org_id"]
        # Validate decodability up front so we fail fast before the network call.
        try:
            base64.b64decode(kwargs["cer_base64"])
            base64.b64decode(kwargs["key_base64"])
        except Exception:
            return ToolResult(
                success=False, error="cer_base64 / key_base64 must decode cleanly."
            )
        payload = {
            "cer": kwargs["cer_base64"],
            "key": kwargs["key_base64"],
            "key_password": kwargs["key_password"],
        }
        try:
            status, body = await _request(
                "POST", f"/api/v1/orgs/{oid}/sat-cert", json_body=payload
            )
            if not _ok(status):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"SAT cert uploaded for org {oid}.",
                data={
                    "org_id": oid,
                    "sat_cert_fingerprint": (
                        body.get("fingerprint") if isinstance(body, dict) else None
                    ),
                },
            )
        except Exception as e:
            logger.error("karafiel_sat_cert_upload failed: %s", e)
            return ToolResult(success=False, error=str(e))


class KarafielPacRegisterTool(BaseTool):
    """Register an org with Karafiel's PAC for CFDI stamping."""

    name = "karafiel_pac_register"
    description = (
        "Register a Karafiel org with the configured PAC (Proveedor "
        "Autorizado de Certificación) for CFDI 4.0 stamping. Requires the "
        "SAT cert to already be uploaded. Returns when the PAC "
        "acknowledges the registration; full onboarding with SAT completes "
        "asynchronously on the PAC side."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"org_id": {"type": "string"}},
            "required": ["org_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        oid = kwargs["org_id"]
        try:
            status, body = await _request(
                "POST", f"/api/v1/orgs/{oid}/pac/register"
            )
            if not _ok(status):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"PAC registration submitted for org {oid}.",
                data={
                    "org_id": oid,
                    "pac_status": (
                        body.get("status") if isinstance(body, dict) else None
                    ),
                },
            )
        except Exception as e:
            logger.error("karafiel_pac_register failed: %s", e)
            return ToolResult(success=False, error=str(e))


class KarafielInvoiceSeriesCreateTool(BaseTool):
    """Create a serie + folio range for a Karafiel org."""

    name = "karafiel_invoice_series_create"
    description = (
        "Create an invoice serie (e.g. 'A') + starting folio (e.g. 1001) "
        "for a Karafiel org. Each invoice issued will increment the folio. "
        "Multiple series can coexist per org (e.g. one per line of business)."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "serie": {"type": "string"},
                "folio_start": {"type": "integer", "default": 1},
            },
            "required": ["org_id", "serie"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        oid = kwargs["org_id"]
        payload = {
            "serie": kwargs["serie"],
            "folio_start": kwargs.get("folio_start", 1),
        }
        try:
            status, body = await _request(
                "POST", f"/api/v1/orgs/{oid}/invoice-series", json_body=payload
            )
            if not _ok(status):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"Series '{payload['serie']}' created for org {oid}.",
                data={"org_id": oid, "serie": payload["serie"]},
            )
        except Exception as e:
            logger.error("karafiel_invoice_series_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_karafiel_provisioning_tools() -> list[BaseTool]:
    return [
        KarafielOrgCreateTool(),
        KarafielSatCertUploadTool(),
        KarafielPacRegisterTool(),
        KarafielInvoiceSeriesCreateTool(),
    ]
