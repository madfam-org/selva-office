"""Market intelligence tools -- DOF, exchange rates, TIIE, UMA, inflation."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class DOFMonitorTool(BaseTool):
    name = "dof_monitor"
    description = (
        "Search the Diario Oficial de la Federacion for regulatory changes "
        "via MADFAM Crawler"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search terms for DOF (e.g. 'reforma fiscal', 'RESICO', "
                        "'salario minimo')"
                    ),
                },
                "since": {
                    "type": "string",
                    "description": (
                        "Optional ISO date to filter results after this date "
                        "(e.g. '2026-01-01')"
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
    description = "Get current USD/MXN exchange rate from Banxico"

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
        from madfam_inference.adapters.banxico import BanxicoAdapter

        currency: str = kwargs.get("currency", "USD")
        adapter = BanxicoAdapter()
        result = await adapter.get_exchange_rate(currency)
        success = bool(result.rate)
        return ToolResult(
            success=success,
            output=(
                f"{result.currency_pair}: {result.rate} "
                f"(fecha: {result.date})"
                if success
                else f"No exchange rate data available for {currency}/MXN"
            ),
            data=result.model_dump(),
        )


class UMATrackerTool(BaseTool):
    name = "uma_tracker"
    description = (
        "Get current UMA (Unidad de Medida y Actualizacion) value from Banxico"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.banxico import BanxicoAdapter

        adapter = BanxicoAdapter()
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
    description = "Get current TIIE interbank interest rate from Banxico"

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
        from madfam_inference.adapters.banxico import BanxicoAdapter

        term: str = kwargs.get("term", "28")
        if term not in ("28", "91"):
            return ToolResult(
                success=False,
                error="term must be '28' or '91'",
            )

        adapter = BanxicoAdapter()
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
    description = "Get current Mexican CPI/INPC annual inflation rate"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.banxico import BanxicoAdapter

        adapter = BanxicoAdapter()
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
