"""Tests for accounting tools -- ISR/IVA, reconciliation, declarations, payments."""

from __future__ import annotations

import pytest

from selva_tools.builtins.accounting import (
    BankReconciliationTool,
    DeclarationPrepTool,
    ISRCalculatorTool,
    IVACalculatorTool,
    PaymentSummaryTool,
)

ACCOUNTING_TOOLS = [
    ("isr_calculate", ISRCalculatorTool),
    ("iva_calculate", IVACalculatorTool),
    ("bank_reconcile", BankReconciliationTool),
    ("declaration_prep", DeclarationPrepTool),
    ("payment_summary", PaymentSummaryTool),
]


class TestAccountingToolsSchema:
    """All accounting tools have valid schemas and metadata."""

    @pytest.mark.parametrize("expected_name,tool_cls", ACCOUNTING_TOOLS)
    def test_tool_name(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert tool.name == expected_name

    @pytest.mark.parametrize("expected_name,tool_cls", ACCOUNTING_TOOLS)
    def test_tool_has_description(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert len(tool.description) > 10

    @pytest.mark.parametrize("expected_name,tool_cls", ACCOUNTING_TOOLS)
    def test_tool_schema_is_valid_json_schema(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert len(schema["required"]) >= 1

    @pytest.mark.parametrize("expected_name,tool_cls", ACCOUNTING_TOOLS)
    def test_tool_openai_spec(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == expected_name


class TestAccountingToolsInRegistry:
    """Accounting tools are registered in get_builtin_tools()."""

    def test_all_accounting_tools_in_registry(self) -> None:
        from selva_tools.builtins import get_builtin_tools

        tools = get_builtin_tools()
        names = {t.name for t in tools}
        for expected_name, _ in ACCOUNTING_TOOLS:
            assert expected_name in names, f"{expected_name} missing from registry"


class TestAccountingToolsMissingInput:
    """Tools return errors on missing required inputs."""

    @pytest.mark.asyncio
    async def test_isr_missing_income(self) -> None:
        tool = ISRCalculatorTool()
        result = await tool.execute()
        assert not result.success
        assert "income" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_iva_missing_amount(self) -> None:
        tool = IVACalculatorTool()
        result = await tool.execute()
        assert not result.success
        assert "amount" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_bank_reconcile_missing_org_id(self) -> None:
        tool = BankReconciliationTool()
        result = await tool.execute(period="2026-04")
        assert not result.success
        assert "org_id" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_bank_reconcile_missing_period(self) -> None:
        tool = BankReconciliationTool()
        result = await tool.execute(org_id="org-1")
        assert not result.success
        assert "period" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_bank_reconcile_invalid_period(self) -> None:
        tool = BankReconciliationTool()
        result = await tool.execute(org_id="org-1", period="invalid")
        assert not result.success
        assert "period" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_declaration_prep_missing_fields(self) -> None:
        tool = DeclarationPrepTool()
        result = await tool.execute(org_id="org-1")
        assert not result.success

    @pytest.mark.asyncio
    async def test_payment_summary_missing_org_id(self) -> None:
        tool = PaymentSummaryTool()
        result = await tool.execute(period="2026-04")
        assert not result.success
        assert "org_id" in (result.error or "").lower()


class TestBankReconciliationToolPeriodParsing:
    """BankReconciliationTool correctly parses YYYY-MM periods."""

    @pytest.mark.asyncio
    async def test_valid_period_no_error(self) -> None:
        """With valid period but no adapters, reconciliation returns success (empty data)."""
        tool = BankReconciliationTool()
        result = await tool.execute(org_id="org-1", period="2026-04")
        assert result.success
        assert result.data["summary"]["period"] == "2026-04"

    @pytest.mark.asyncio
    async def test_december_period_wraps_year(self) -> None:
        tool = BankReconciliationTool()
        result = await tool.execute(org_id="org-1", period="2026-12")
        assert result.success
        assert result.data["summary"]["period"] == "2026-12"

    @pytest.mark.asyncio
    async def test_reconciliation_empty_data(self) -> None:
        """Without adapters, reconciliation returns zero counts."""
        tool = BankReconciliationTool()
        result = await tool.execute(org_id="org-1", period="2026-04")
        assert result.data["summary"]["total_bank_txns"] == 0
        assert result.data["summary"]["total_cfdis"] == 0
        assert result.data["summary"]["matched_count"] == 0
