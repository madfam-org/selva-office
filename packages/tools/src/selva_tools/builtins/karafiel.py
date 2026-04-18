"""Karafiel compliance tools -- RFC validation, CFDI, blacklist, constancia, NOM-035."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class RFCValidationTool(BaseTool):
    name = "rfc_validation"
    description = "Validate a Mexican RFC (tax ID) via the Karafiel SAT module"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rfc": {
                    "type": "string",
                    "description": "RFC string to validate (e.g. 'XAXX010101000')",
                },
            },
            "required": ["rfc"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        rfc: str = kwargs.get("rfc", "")
        if not rfc:
            return ToolResult(success=False, error="rfc is required")

        adapter = KarafielAdapter()
        result = await adapter.validate_rfc(rfc)
        return ToolResult(
            success=result.valid,
            output=f"RFC {result.rfc}: valid={result.valid}, status={result.status}",
            data=result.model_dump(),
        )


class CFDIGenerateTool(BaseTool):
    name = "cfdi_generate"
    description = "Generate a CFDI 4.0 XML invoice via the Karafiel CFDI module"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "emisor_rfc": {
                    "type": "string",
                    "description": "Issuer RFC",
                },
                "receptor_rfc": {
                    "type": "string",
                    "description": "Receiver RFC",
                },
                "conceptos": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Invoice line items (conceptos)",
                },
                "forma_pago": {
                    "type": "string",
                    "default": "01",
                    "description": "Payment form code (c_FormaPago)",
                },
                "metodo_pago": {
                    "type": "string",
                    "default": "PUE",
                    "description": "Payment method (PUE or PPD)",
                },
            },
            "required": ["emisor_rfc", "receptor_rfc", "conceptos"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        emisor_rfc: str = kwargs.get("emisor_rfc", "")
        receptor_rfc: str = kwargs.get("receptor_rfc", "")
        conceptos: list[dict[str, Any]] = kwargs.get("conceptos", [])
        forma_pago: str = kwargs.get("forma_pago", "01")
        metodo_pago: str = kwargs.get("metodo_pago", "PUE")

        if not emisor_rfc or not receptor_rfc or not conceptos:
            return ToolResult(
                success=False, error="emisor_rfc, receptor_rfc, and conceptos are required"
            )

        adapter = KarafielAdapter()
        result = await adapter.generate_cfdi(
            emisor_rfc=emisor_rfc,
            receptor_rfc=receptor_rfc,
            conceptos=conceptos,
            forma_pago=forma_pago,
            metodo_pago=metodo_pago,
        )
        success = bool(result.uuid) and not result.status.startswith("error")
        return ToolResult(
            success=success,
            output=f"CFDI {result.uuid or 'N/A'}: status={result.status}",
            data=result.model_dump(),
        )


class CFDIStampTool(BaseTool):
    name = "cfdi_stamp"
    description = "Stamp a CFDI XML via PAC through the Karafiel CFDI module"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cfdi_xml": {
                    "type": "string",
                    "description": "CFDI XML content to stamp",
                },
            },
            "required": ["cfdi_xml"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        cfdi_xml: str = kwargs.get("cfdi_xml", "")
        if not cfdi_xml:
            return ToolResult(success=False, error="cfdi_xml is required")

        adapter = KarafielAdapter()
        result = await adapter.stamp_cfdi(cfdi_xml)
        success = bool(result.folio_fiscal) and not result.status.startswith("error")
        return ToolResult(
            success=success,
            output=f"Stamp folio={result.folio_fiscal or 'N/A'}: status={result.status}",
            data=result.model_dump(),
        )


class CFDIStatusTool(BaseTool):
    name = "cfdi_status"
    description = "Check the status of a CFDI by UUID via the Karafiel CFDI module"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "CFDI UUID (folio fiscal) to check",
                },
            },
            "required": ["uuid"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        uuid: str = kwargs.get("uuid", "")
        if not uuid:
            return ToolResult(success=False, error="uuid is required")

        adapter = KarafielAdapter()
        result = await adapter.get_cfdi_status(uuid)
        success = not result.estado.startswith("error")
        return ToolResult(
            success=success,
            output=f"CFDI {result.uuid}: estado={result.estado}",
            data=result.model_dump(),
        )


class BlacklistCheckTool(BaseTool):
    name = "blacklist_check"
    description = "Check if an RFC is on the SAT Article 69-B blacklist via Karafiel"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rfc": {
                    "type": "string",
                    "description": "RFC to check against the Article 69-B blacklist",
                },
            },
            "required": ["rfc"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        rfc: str = kwargs.get("rfc", "")
        if not rfc:
            return ToolResult(success=False, error="rfc is required")

        adapter = KarafielAdapter()
        result = await adapter.check_blacklist(rfc)
        return ToolResult(
            success=True,
            output=(
                f"RFC {result.rfc}: listed={result.listed}, "
                f"article_69b={result.article_69b}, definitive={result.definitive}"
            ),
            data=result.model_dump(),
        )


class ConstanciaFiscalTool(BaseTool):
    name = "constancia_fiscal"
    description = (
        "Look up Constancia de Situacion Fiscal for an RFC via Karafiel SAT portal"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rfc": {
                    "type": "string",
                    "description": "RFC to look up (e.g. 'XAXX010101000')",
                },
            },
            "required": ["rfc"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        rfc: str = kwargs.get("rfc", "")
        if not rfc:
            return ToolResult(success=False, error="rfc is required")

        adapter = KarafielAdapter()
        result = await adapter.get_constancia(rfc)
        success = not result.situacion.startswith("error")
        return ToolResult(
            success=success,
            output=(
                f"RFC {result.rfc}: situacion={result.situacion}, "
                f"regimen={result.regimen_fiscal}"
            ),
            data=result.model_dump(),
        )


class ComplementoPagoTool(BaseTool):
    name = "complemento_pago"
    description = (
        "Generate Complemento de Pagos CFDI for partial payments via Karafiel"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cfdi_uuid": {
                    "type": "string",
                    "description": "UUID of the original CFDI being paid",
                },
                "monto_pagado": {
                    "type": "string",
                    "description": "Amount paid (e.g. '5000.00')",
                },
                "fecha_pago": {
                    "type": "string",
                    "description": "Payment date in ISO format (e.g. '2026-04-14')",
                },
                "forma_pago": {
                    "type": "string",
                    "description": "Payment form code (c_FormaPago, e.g. '03' for transfer)",
                    "default": "03",
                },
            },
            "required": ["cfdi_uuid", "monto_pagado", "fecha_pago"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        cfdi_uuid: str = kwargs.get("cfdi_uuid", "")
        monto_pagado: str = kwargs.get("monto_pagado", "")
        fecha_pago: str = kwargs.get("fecha_pago", "")
        forma_pago: str = kwargs.get("forma_pago", "03")

        if not cfdi_uuid or not monto_pagado or not fecha_pago:
            return ToolResult(
                success=False,
                error="cfdi_uuid, monto_pagado, and fecha_pago are required",
            )

        adapter = KarafielAdapter()
        result = await adapter.generate_complemento_pago(
            cfdi_uuid=cfdi_uuid,
            payment_data={
                "monto_pagado": monto_pagado,
                "fecha_pago": fecha_pago,
                "forma_pago": forma_pago,
            },
        )
        success = bool(result.uuid) and not result.status.startswith("error")
        return ToolResult(
            success=success,
            output=f"Complemento {result.uuid or 'N/A'}: status={result.status}",
            data=result.model_dump(),
        )


class NOM035SurveyTool(BaseTool):
    name = "nom035_survey"
    description = (
        "Generate NOM-035 psychosocial risk survey via Karafiel compliance module"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier",
                },
                "survey_type": {
                    "type": "string",
                    "description": "Survey type: 'general' or 'specific'",
                    "enum": ["general", "specific"],
                    "default": "general",
                },
            },
            "required": ["org_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        org_id: str = kwargs.get("org_id", "")
        survey_type: str = kwargs.get("survey_type", "general")

        if not org_id:
            return ToolResult(success=False, error="org_id is required")

        adapter = KarafielAdapter()
        result = await adapter.generate_nom035_survey(org_id, survey_type)
        success = not result.status.startswith("error")
        return ToolResult(
            success=success,
            output=f"NOM-035 survey ({survey_type}): status={result.status}",
            data=result.data,
        )


class NOM035ReportTool(BaseTool):
    name = "nom035_report"
    description = "Generate NOM-035 STPS compliance report via Karafiel"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier",
                },
                "survey_results": {
                    "type": "object",
                    "description": "Completed survey results to analyze",
                },
            },
            "required": ["org_id", "survey_results"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        org_id: str = kwargs.get("org_id", "")
        survey_results: dict[str, Any] = kwargs.get("survey_results", {})

        if not org_id or not survey_results:
            return ToolResult(
                success=False,
                error="org_id and survey_results are required",
            )

        adapter = KarafielAdapter()
        result = await adapter.generate_nom035_report(org_id, survey_results)
        success = not result.status.startswith("error")
        return ToolResult(
            success=success,
            output=f"NOM-035 report for org {org_id}: status={result.status}",
            data=result.data,
        )
