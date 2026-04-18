"""Tests for market intelligence tools."""

from __future__ import annotations

import pytest

from selva_tools.builtins.intelligence import (
    DOFMonitorTool,
    ExchangeRateTool,
    InflationTool,
    TIIETool,
    UMATrackerTool,
)

INTELLIGENCE_TOOLS = [
    ("dof_monitor", DOFMonitorTool),
    ("exchange_rate", ExchangeRateTool),
    ("uma_tracker", UMATrackerTool),
    ("tiie_rate", TIIETool),
    ("inflation_rate", InflationTool),
]


class TestIntelligenceToolsSchema:
    """All intelligence tools have valid schemas and metadata."""

    @pytest.mark.parametrize("expected_name,tool_cls", INTELLIGENCE_TOOLS)
    def test_tool_name(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert tool.name == expected_name

    @pytest.mark.parametrize("expected_name,tool_cls", INTELLIGENCE_TOOLS)
    def test_tool_has_description(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert len(tool.description) > 10

    @pytest.mark.parametrize("expected_name,tool_cls", INTELLIGENCE_TOOLS)
    def test_tool_schema_is_valid_json_schema(
        self, expected_name: str, tool_cls: type
    ) -> None:
        tool = tool_cls()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    @pytest.mark.parametrize("expected_name,tool_cls", INTELLIGENCE_TOOLS)
    def test_tool_openai_spec(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == expected_name


class TestIntelligenceToolsInRegistry:
    """Intelligence tools are registered in get_builtin_tools()."""

    def test_all_intelligence_tools_in_registry(self) -> None:
        from selva_tools.builtins import get_builtin_tools

        tools = get_builtin_tools()
        names = {t.name for t in tools}
        for expected_name, _ in INTELLIGENCE_TOOLS:
            assert expected_name in names, f"{expected_name} missing from registry"


class TestDOFMonitorRequiredInput:
    """DOFMonitorTool validates required inputs."""

    @pytest.mark.asyncio
    async def test_missing_query(self) -> None:
        tool = DOFMonitorTool()
        result = await tool.execute()
        assert not result.success
        assert "query" in (result.error or "").lower()

    def test_dof_schema_requires_query(self) -> None:
        tool = DOFMonitorTool()
        schema = tool.parameters_schema()
        assert "query" in schema["required"]


class TestTIIEToolValidation:
    """TIIETool validates term parameter."""

    @pytest.mark.asyncio
    async def test_invalid_term(self) -> None:
        tool = TIIETool()
        result = await tool.execute(term="365")
        assert not result.success
        assert "28" in (result.error or "")
        assert "91" in (result.error or "")


class TestExchangeRateToolDefaults:
    """ExchangeRateTool has sensible defaults."""

    def test_currency_default(self) -> None:
        tool = ExchangeRateTool()
        schema = tool.parameters_schema()
        currency_prop = schema["properties"]["currency"]
        assert currency_prop["default"] == "USD"

    def test_no_required_params(self) -> None:
        tool = ExchangeRateTool()
        schema = tool.parameters_schema()
        assert schema["required"] == []


class TestUMATrackerToolDefaults:
    """UMATrackerTool has no required parameters."""

    def test_no_required_params(self) -> None:
        tool = UMATrackerTool()
        schema = tool.parameters_schema()
        assert schema["required"] == []


class TestInflationToolDefaults:
    """InflationTool has no required parameters."""

    def test_no_required_params(self) -> None:
        tool = InflationTool()
        schema = tool.parameters_schema()
        assert schema["required"] == []
