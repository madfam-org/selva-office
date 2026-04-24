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
        "Reconcile bank transactions from Dhanam against CFDI records from Karafiel "
        "for a given period. Matches by amount, date proximity, and counterparty RFC. "
        "Returns matched pairs, unmatched bank items, and unmatched CFDIs."
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
        org_id = kwargs.get("org_id", "")
        period = kwargs.get("period", "")
        rfc = kwargs.get("rfc", "")

        if not org_id or not period:
            return ToolResult(success=False, error="org_id and period are required")

        # Derive date range from period (YYYY-MM).
        try:
            year, month = period.split("-")
            since = f"{year}-{month}-01"
            m = int(month)
            until = f"{int(year) + 1}-01-01" if m == 12 else f"{year}-{m + 1:02d}-01"
        except ValueError:
            return ToolResult(
                success=False,
                error=f"Invalid period format '{period}'; expected YYYY-MM",
            )

        # Fetch bank transactions from Dhanam.
        bank_txns: list[dict[str, Any]] = []
        try:
            from madfam_inference.adapters.dhanam import DhanamAdapter

            dhanam = DhanamAdapter()
            txns = await dhanam.list_transactions(org_id, since, until)
            bank_txns = [t.model_dump() for t in txns]
        except Exception:
            pass  # Graceful degradation; reconciliation proceeds with empty bank data.

        # Fetch CFDIs from Karafiel.
        cfdis: list[dict[str, Any]] = []
        if rfc:
            try:
                from madfam_inference.adapters.karafiel import KarafielAdapter

                karafiel = KarafielAdapter()
                cfdi_items = await karafiel.list_cfdis(rfc, since, until)
                cfdis = [c.model_dump() for c in cfdi_items]
            except Exception:
                pass

        # Match bank transactions to CFDIs by amount + counterparty_rfc.
        matched: list[dict[str, Any]] = []
        unmatched_cfdi_indices: set[int] = set(range(len(cfdis)))

        for txn in bank_txns:
            txn_amount = txn.get("amount", "")
            txn_rfc = txn.get("counterparty_rfc", "")
            found_match = False

            for idx in list(unmatched_cfdi_indices):
                cfdi = cfdis[idx]
                if cfdi.get("total") == txn_amount and (
                    not txn_rfc
                    or cfdi.get("receptor_rfc") == txn_rfc
                    or cfdi.get("emisor_rfc") == txn_rfc
                ):
                    matched.append({"bank_txn": txn, "cfdi": cfdi})
                    unmatched_cfdi_indices.discard(idx)
                    found_match = True
                    break

            if not found_match:
                matched.append({"bank_txn": txn, "cfdi": None})

        unmatched_cfdis = [cfdis[i] for i in sorted(unmatched_cfdi_indices)]
        unmatched_bank = [m["bank_txn"] for m in matched if m["cfdi"] is None]
        fully_matched = [m for m in matched if m["cfdi"] is not None]

        summary = {
            "period": period,
            "total_bank_txns": len(bank_txns),
            "total_cfdis": len(cfdis),
            "matched_count": len(fully_matched),
            "unmatched_bank_count": len(unmatched_bank),
            "unmatched_cfdi_count": len(unmatched_cfdis),
        }

        return ToolResult(
            success=True,
            output=(
                f"Reconciliation {period}: {len(fully_matched)} matched, "
                f"{len(unmatched_bank)} unmatched bank, "
                f"{len(unmatched_cfdis)} unmatched CFDIs"
            ),
            data={
                "summary": summary,
                "matched": fully_matched,
                "unmatched_bank": unmatched_bank,
                "unmatched_cfdis": unmatched_cfdis,
            },
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
        "Get payment method breakdown from Dhanam for a period. "
        "Returns totals by Stripe MX, OXXO, SPEI, Conekta, and transfer."
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

        adapter = DhanamAdapter()
        result = await adapter.get_payment_summary(org_id, period)
        return ToolResult(
            success=True,
            output=(
                f"Payment summary {result.period}: income={result.total_income}, "
                f"expenses={result.total_expenses}"
            ),
            data=result.model_dump(),
        )
