"""Market intelligence tools -- DOF, exchange rates, TIIE, UMA, inflation."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class DOFMonitorTool(BaseTool):
    name = "dof_monitor"
    description = (
        "Search the Diario Oficial de la Federacion for regulatory changes via MADFAM Crawler"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search terms for DOF (e.g. 'reforma fiscal', 'RESICO', 'salario minimo')"
                    ),
                },
                "since": {
                    "type": "string",
                    "description": (
                        "Optional ISO date to filter results after this date (e.g. '2026-01-01')"
                    ),
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.crawler import CrawlerAdapter

        query: str = kwargs.get("query", "")
        if not query:
            return ToolResult(success=False, error="query is required")

        since: str | None = kwargs.get("since")
        adapter = CrawlerAdapter()
        results = await adapter.search_dof(query, since=since)
        return ToolResult(
            success=True,
            output=f"DOF search for '{query}': {len(results)} entries found",
            data={"entries": results, "count": len(results)},
        )


class ExchangeRateTool(BaseTool):
    name = "exchange_rate"
    description = "Get current USD/MXN exchange rate via Dhanam market data API"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "default": "USD",
                    "description": "Currency code (default: USD)",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.dhanam import DhanamAdapter

        currency: str = kwargs.get("currency", "USD")
        adapter = DhanamAdapter()
        result = await adapter.get_exchange_rate(currency)
        success = bool(result.rate)
        return ToolResult(
            success=success,
            output=(
                f"{result.currency_pair}: {result.rate} (fecha: {result.date})"
                if success
                else f"No exchange rate data available for {currency}/MXN"
            ),
            data=result.model_dump(),
        )


class UMATrackerTool(BaseTool):
    name = "uma_tracker"
    description = "Get current UMA (Unidad de Medida y Actualizacion) value via Dhanam"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.dhanam import DhanamAdapter

        adapter = DhanamAdapter()
        result = await adapter.get_uma()
        success = bool(result.value)
        return ToolResult(
            success=success,
            output=(
                f"UMA diaria: ${result.value} MXN (fecha: {result.date})"
                if success
                else "No UMA data available"
            ),
            data=result.model_dump(),
        )


class TIIETool(BaseTool):
    name = "tiie_rate"
    description = "Get current TIIE interbank interest rate via Dhanam"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "term": {
                    "type": "string",
                    "default": "28",
                    "description": "TIIE term in days: '28' or '91'",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.dhanam import DhanamAdapter

        term: str = kwargs.get("term", "28")
        if term not in ("28", "91"):
            return ToolResult(
                success=False,
                error="term must be '28' or '91'",
            )

        adapter = DhanamAdapter()
        result = await adapter.get_tiie(term)
        success = bool(result.value)
        return ToolResult(
            success=success,
            output=(
                f"TIIE {term} dias: {result.value}% (fecha: {result.date})"
                if success
                else f"No TIIE data available for {term}-day term"
            ),
            data=result.model_dump(),
        )


class InflationTool(BaseTool):
    name = "inflation_rate"
    description = "Get current Mexican CPI/INPC annual inflation rate via Dhanam"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.dhanam import DhanamAdapter

        adapter = DhanamAdapter()
        result = await adapter.get_inflation()
        success = bool(result.value)
        return ToolResult(
            success=success,
            output=(
                f"Inflacion anual (INPC): {result.value}% (fecha: {result.date})"
                if success
                else "No inflation data available"
            ),
            data=result.model_dump(),
        )


class SATMonitorTool(BaseTool):
    name = "sat_monitor"
    description = "Check RFC tax obligation status and alerts via Karafiel SAT module"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rfc": {
                    "type": "string",
                    "description": ("RFC to check obligations for (e.g. 'XAXX010101000')"),
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
        result = await adapter.get_sat_obligations(rfc)
        success = not result.get("status", "").startswith("error")
        return ToolResult(
            success=success,
            output=(
                f"SAT obligations for RFC {rfc}: "
                f"{result.get('pending_count', 0)} pending, "
                f"{result.get('alert_count', 0)} alert(s)"
            ),
            data=result,
        )


class SIEMComplianceTool(BaseTool):
    name = "siem_compliance"
    description = "Check SIEM (Sistema de Informacion Empresarial Mexicano) registration status"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rfc": {
                    "type": "string",
                    "description": "RFC of the entity to check SIEM status for",
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
        result = await adapter.get_siem_status(rfc)
        success = not result.get("status", "").startswith("error")
        return ToolResult(
            success=success,
            output=(
                f"SIEM status for RFC {rfc}: "
                f"registered={result.get('registered', False)}, "
                f"renewal_date={result.get('renewal_date', 'N/A')}"
            ),
            data=result,
        )
