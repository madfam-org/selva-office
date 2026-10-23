"""Accounting tools -- ISR/IVA calculation, bank reconciliation, declarations, payments."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class ISRCalculatorTool(BaseTool):
    """Compute ISR (income tax) via Karafiel's fiscal module."""

    name = "isr_calculate"
    description = (
        "Calculate Mexican ISR (Impuesto Sobre la Renta) for a given income amount, "
        "period, and fiscal regime via the Karafiel compliance engine"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "income": {
                    "type": "number",
                    "description": "Gross income amount in MXN",
                },
                "period": {
                    "type": "string",
                    "enum": ["monthly", "annual"],
                    "description": (
                        "Tax period (monthly for provisional, annual for declaracion anual)"
                    ),
                },
                "regime": {
                    "type": "string",
                    "description": (
                        "Fiscal regime code (pf=persona fisica, pm=persona moral, resico)"
                    ),
                    "default": "pf",
                },
            },
            "required": ["income"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        income = kwargs.get("income")
        if income is None:
            return ToolResult(success=False, error="income is required")

        period = kwargs.get("period", "monthly")
        regime = kwargs.get("regime", "pf")

        adapter = KarafielAdapter()
        result = await adapter.compute_isr(income=float(income), period=period, regime=regime)
        has_error = bool(result.details.get("error"))
        return ToolResult(
            success=not has_error,
            output=(f"ISR: base={result.base_amount}, tax={result.tax_amount}, rate={result.rate}"),
            data=result.model_dump(),
            error=result.details.get("error") if has_error else None,
        )


class IVACalculatorTool(BaseTool):
    """Compute IVA (value-added tax) via Karafiel's fiscal module."""

    name = "iva_calculate"
    description = (
        "Calculate Mexican IVA (Impuesto al Valor Agregado) for a given amount, "
        "rate, and retention flag via the Karafiel compliance engine"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Taxable amount in MXN",
                },
                "rate": {
                    "type": "number",
                    "description": "IVA rate (0.16 standard, 0.08 frontera, 0.0 exento)",
                    "default": 0.16,
                },
                "retained": {
                    "type": "boolean",
                    "description": "Whether IVA is retained (retenido)",
                    "default": False,
                },
            },
            "required": ["amount"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        amount = kwargs.get("amount")
        if amount is None:
            return ToolResult(success=False, error="amount is required")

        rate = kwargs.get("rate", 0.16)
        retained = kwargs.get("retained", False)

        adapter = KarafielAdapter()
        result = await adapter.compute_iva(
            amount=float(amount), rate=float(rate), retained=bool(retained)
        )
        has_error = bool(result.details.get("error"))
        return ToolResult(
            success=not has_error,
            output=(f"IVA: base={result.base_amount}, tax={result.tax_amount}, rate={result.rate}"),
            data=result.model_dump(),
            error=result.details.get("error") if has_error else None,
        )


class BankReconciliationTool(BaseTool):
    """Match bank transactions against CFDIs for reconciliation (Selva orchestration)."""

    name = "bank_reconcile"
    description = (
        "Report period-reconciliation availability. Currently unavailable pending "
        "complete, scoped Dhanam and Karafiel source contracts; does not perform matching."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier",
                },
                "period": {
                    "type": "string",
                    "description": "Period in YYYY-MM format (e.g. '2026-04')",
                },
                "rfc": {
                    "type": "string",
                    "description": "Emisor RFC to list CFDIs for",
                },
            },
            "required": ["org_id", "period"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not kwargs.get("org_id") or not kwargs.get("period"):
            return ToolResult(success=False, error="org_id and period are required")
        return ToolResult(
            success=False,
            error="Bank reconciliation unavailable: complete scoped source contracts are required",
            data={"coverage_status": "unavailable"},
        )


class DeclarationPrepTool(BaseTool):
    """Prepare a tax declaration via Karafiel's fiscal module."""

    name = "declaration_prep"
    description = (
        "Prepare monthly or periodic tax declaration data via Karafiel. "
        "Supports ISR provisional, IVA mensual, and DIOT declarations."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier",
                },
                "period": {
                    "type": "string",
                    "description": "Period in YYYY-MM format",
                },
                "declaration_type": {
                    "type": "string",
                    "enum": ["isr_provisional", "iva_mensual", "diot"],
                    "description": "Type of tax declaration to prepare",
                },
                "income": {
                    "type": "number",
                    "description": "Total income for the period in MXN",
                    "default": 0.0,
                },
                "expenses": {
                    "type": "number",
                    "description": "Total deductible expenses in MXN",
                    "default": 0.0,
                },
            },
            "required": ["org_id", "period", "declaration_type"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.karafiel import KarafielAdapter

        org_id = kwargs.get("org_id", "")
        period = kwargs.get("period", "")
        declaration_type = kwargs.get("declaration_type", "")

        if not org_id or not period or not declaration_type:
            return ToolResult(
                success=False,
                error="org_id, period, and declaration_type are required",
            )

        income = float(kwargs.get("income", 0.0))
        expenses = float(kwargs.get("expenses", 0.0))

        adapter = KarafielAdapter()
        result = await adapter.build_declaration(
            org_id=org_id,
            period=period,
            declaration_type=declaration_type,
            income=income,
            expenses=expenses,
        )
        has_error = result.status.startswith("error")
        return ToolResult(
            success=not has_error,
            output=(
                f"Declaration {result.declaration_type} for {result.period}: status={result.status}"
            ),
            data=result.model_dump(),
            error=result.status if has_error else None,
        )


class PaymentSummaryTool(BaseTool):
    """Fetch payment summary from Dhanam by period."""

    name = "payment_summary"
    description = (
        "Report payment-summary availability for a period. The legacy source contract "
        "is currently unavailable; no income or expense totals are inferred."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization identifier",
                },
                "period": {
                    "type": "string",
                    "description": "Period in YYYY-MM format",
                },
            },
            "required": ["org_id", "period"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        from madfam_inference.adapters.dhanam import DhanamAdapter

        org_id = kwargs.get("org_id", "")
        period = kwargs.get("period", "")

        if not org_id or not period:
            return ToolResult(success=False, error="org_id and period are required")

        try:
            result = await DhanamAdapter().get_payment_summary(org_id, period)
        except Exception:
            return ToolResult(
                success=False,
                error="Payment summary unavailable; no totals were established",
                data={"coverage_status": "unavailable"},
            )
        return ToolResult(
            success=True,
            output=(
                f"Payment summary {result.period}: income={result.total_income}, "
                f"expenses={result.total_expenses}"
            ),
            data=result.model_dump(),
        )
