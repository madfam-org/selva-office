"""LFPDPPP data privacy tools -- PII detection, privacy notices, data deletion."""

from __future__ import annotations

import re
from typing import Any

from ..base import BaseTool, ToolResult

# Mexican PII patterns
RFC_PATTERN = re.compile(r"[A-Z\xd1&]{3,4}\d{6}[A-Z0-9]{3}")
CURP_PATTERN = re.compile(r"[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_MX_PATTERN = re.compile(r"(?:\+?52)?[\s-]?\d{2,3}[\s-]?\d{3,4}[\s-]?\d{4}")
CLABE_PATTERN = re.compile(r"\d{18}")


class PIIClassificationTool(BaseTool):
    name = "pii_classify"
    description = "Scan text for Mexican PII patterns (RFC, CURP, email, phone, CLABE)"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to scan for PII"},
            },
            "required": ["text"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        text: str = kwargs.get("text", "")
        if not text:
            return ToolResult(success=False, error="Text is required")

        findings: list[dict[str, Any]] = []
        for name, pattern in [
            ("RFC", RFC_PATTERN),
            ("CURP", CURP_PATTERN),
            ("email", EMAIL_PATTERN),
            ("phone", PHONE_MX_PATTERN),
            ("CLABE", CLABE_PATTERN),
        ]:
            matches = pattern.findall(text)
            if matches:
                findings.append(
                    {
                        "type": name,
                        "count": len(matches),
                        "redacted": [m[:4] + "***" for m in matches[:3]],
                    }
                )

        has_pii = len(findings) > 0
        return ToolResult(
            success=True,
            output=f"{'PII detected' if has_pii else 'No PII found'}: {len(findings)} types",
            data={"has_pii": has_pii, "findings": findings},
        )


class PrivacyNoticeGeneratorTool(BaseTool):
    name = "privacy_notice_generate"
    description = "Generate an aviso de privacidad (LFPDPPP privacy notice) from tenant config"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "razon_social": {
                    "type": "string",
                    "description": "Legal business name (razon social)",
                },
                "rfc": {
                    "type": "string",
                    "description": "RFC of the data controller",
                },
                "domicilio": {
                    "type": "string",
                    "description": "Fiscal address (domicilio fiscal)",
                },
                "data_purposes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of data processing purposes",
                },
                "contact_email": {
                    "type": "string",
                    "description": "ARCO rights contact email",
                },
            },
            "required": ["razon_social", "rfc"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        razon: str = kwargs.get("razon_social", "")
        rfc: str = kwargs.get("rfc", "")
        domicilio: str = kwargs.get("domicilio", "")
        purposes: list[str] = kwargs.get(
            "data_purposes",
            [
                "Prestacion de servicios",
                "Facturacion",
                "Comunicacion comercial",
            ],
        )
        email: str = kwargs.get(
            "contact_email",
            f"privacidad@{razon.lower().replace(' ', '')}.com",
        )

        if not razon or not rfc:
            return ToolResult(success=False, error="razon_social and rfc are required")

        purposes_text = "\n".join(f"  - {p}" for p in purposes)

        notice = (
            f"AVISO DE PRIVACIDAD\n\n"
            f"En cumplimiento con la Ley Federal de Proteccion de Datos Personales "
            f"en Posesion de los Particulares (LFPDPPP), {razon} con RFC {rfc}, "
            f"domiciliado en {domicilio or '[domicilio fiscal]'}, "
            f"hace de su conocimiento:\n\n"
            f"FINALIDADES DEL TRATAMIENTO:\n{purposes_text}\n\n"
            f"DERECHOS ARCO:\n"
            f"Usted tiene derecho a Acceder, Rectificar, Cancelar u Oponerse al "
            f"tratamiento de sus datos personales. Para ejercer estos derechos, "
            f"comuniquese a: {email}\n\n"
            f"TRANSFERENCIAS:\n"
            f"Sus datos podran ser transferidos a terceros nacionales para las "
            f"finalidades descritas, con su consentimiento expreso.\n\n"
            f"CAMBIOS AL AVISO:\n"
            f"Este aviso podra ser modificado. La version actualizada estara "
            f"disponible en nuestro sitio web."
        )

        return ToolResult(
            success=True,
            output=notice,
            data={"razon_social": razon, "rfc": rfc, "word_count": len(notice.split())},
        )


class DataDeletionTool(BaseTool):
    name = "data_deletion_search"
    description = (
        "Search for PII across artifacts, memory, and events for LFPDPPP right-to-deletion requests"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "RFC, email, name, or CURP to search for",
                },
                "scope": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["artifacts", "events", "chat", "memory"],
                    },
                    "default": ["artifacts", "events", "chat", "memory"],
                    "description": "Data stores to search",
                },
            },
            "required": ["search_term"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        term: str = kwargs.get("search_term", "")
        scope: list[str] = kwargs.get("scope", ["artifacts", "events", "chat", "memory"])

        if not term:
            return ToolResult(success=False, error="search_term is required")

        # This tool SEARCHES but does not delete -- deletion requires HITL approval.
        # In a full implementation it would query each data store.
        return ToolResult(
            success=True,
            output=(
                f"Data deletion search for '{term[:20]}...' across "
                f"{len(scope)} stores. Manual review required before deletion."
            ),
            data={
                "search_term": term,
                "scopes_searched": scope,
                "status": "requires_hitl_approval",
                "note": (
                    "Actual deletion requires human approval via the approval gate. "
                    "This tool only identifies records."
                ),
            },
        )
