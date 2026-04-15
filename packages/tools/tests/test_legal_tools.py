"""Tests for legal tools (contract generate, REPSE check, law search, compliance)."""

from __future__ import annotations

import pytest

from autoswarm_tools.builtins.legal import (
    ComplianceCheckTool,
    ContractGenerateTool,
    LawSearchTool,
    REPSECheckTool,
)

LEGAL_TOOLS = [
    ("contract_generate", ContractGenerateTool),
    ("repse_check", REPSECheckTool),
    ("law_search", LawSearchTool),
    ("compliance_check", ComplianceCheckTool),
]


class TestLegalToolsSchema:
    """All legal tools have valid schemas and metadata."""

    @pytest.mark.parametrize("expected_name,tool_cls", LEGAL_TOOLS)
    def test_tool_name(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert tool.name == expected_name

    @pytest.mark.parametrize("expected_name,tool_cls", LEGAL_TOOLS)
    def test_tool_has_description(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert len(tool.description) > 10

    @pytest.mark.parametrize("expected_name,tool_cls", LEGAL_TOOLS)
    def test_tool_schema_is_valid_json_schema(
        self, expected_name: str, tool_cls: type
    ) -> None:
        tool = tool_cls()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert len(schema["required"]) >= 1

    @pytest.mark.parametrize("expected_name,tool_cls", LEGAL_TOOLS)
    def test_tool_openai_spec(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == expected_name


class TestLegalToolsInRegistry:
    """Legal tools are registered in get_builtin_tools()."""

    def test_all_legal_tools_in_registry(self) -> None:
        from autoswarm_tools.builtins import get_builtin_tools

        tools = get_builtin_tools()
        names = {t.name for t in tools}
        for expected_name, _ in LEGAL_TOOLS:
            assert expected_name in names, f"{expected_name} missing from registry"


class TestLegalToolsMissingInput:
    """Tools return errors on missing required inputs."""

    @pytest.mark.asyncio
    async def test_contract_generate_missing_type(self) -> None:
        tool = ContractGenerateTool()
        result = await tool.execute()
        assert not result.success
        err = (result.error or "").lower()
        assert "contract_type" in err or "required" in err

    @pytest.mark.asyncio
    async def test_contract_generate_missing_parties(self) -> None:
        tool = ContractGenerateTool()
        result = await tool.execute(contract_type="nda")
        assert not result.success

    @pytest.mark.asyncio
    async def test_repse_check_missing_rfc(self) -> None:
        tool = REPSECheckTool()
        result = await tool.execute()
        assert not result.success
        assert "rfc" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_law_search_missing_query(self) -> None:
        tool = LawSearchTool()
        result = await tool.execute()
        assert not result.success
        assert "query" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_compliance_check_missing_domain(self) -> None:
        tool = ComplianceCheckTool()
        result = await tool.execute()
        assert not result.success
        assert "domain" in (result.error or "").lower()


class TestLawSearchToolExecution:
    """LawSearchTool returns structured results."""

    @pytest.mark.asyncio
    async def test_law_search_no_results(self) -> None:
        from unittest.mock import AsyncMock, patch

        mock_adapter = AsyncMock()
        mock_adapter.search_laws.return_value = []

        with patch(
            "madfam_inference.adapters.tezca.TezcaAdapter",
            return_value=mock_adapter,
        ):
            tool = LawSearchTool()
            result = await tool.execute(query="nonexistent")

        assert result.success
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_law_search_with_results(self) -> None:
        from unittest.mock import AsyncMock, patch

        from madfam_inference.adapters.tezca import LawArticle

        mock_adapter = AsyncMock()
        mock_adapter.search_laws.return_value = [
            LawArticle(ley="LFT", articulo="12", titulo="Intermediario"),
        ]

        with patch(
            "madfam_inference.adapters.tezca.TezcaAdapter",
            return_value=mock_adapter,
        ):
            tool = LawSearchTool()
            result = await tool.execute(query="subcontratacion")

        assert result.success
        assert result.data["count"] == 1
        assert len(result.data["articles"]) == 1
        assert "LFT" in result.output


class TestComplianceCheckToolExecution:
    """ComplianceCheckTool returns structured results."""

    @pytest.mark.asyncio
    async def test_compliance_check_compliant(self) -> None:
        from unittest.mock import AsyncMock, patch

        from madfam_inference.adapters.tezca import ComplianceCheck

        mock_adapter = AsyncMock()
        mock_adapter.check_compliance.return_value = ComplianceCheck(
            domain="fiscal", compliant=True
        )

        with patch(
            "madfam_inference.adapters.tezca.TezcaAdapter",
            return_value=mock_adapter,
        ):
            tool = ComplianceCheckTool()
            result = await tool.execute(domain="fiscal")

        assert result.success
        assert "compliant" in result.output

    @pytest.mark.asyncio
    async def test_compliance_check_non_compliant(self) -> None:
        from unittest.mock import AsyncMock, patch

        from madfam_inference.adapters.tezca import ComplianceCheck

        mock_adapter = AsyncMock()
        mock_adapter.check_compliance.return_value = ComplianceCheck(
            domain="laboral",
            compliant=False,
            issues=["Missing REPSE"],
        )

        with patch(
            "madfam_inference.adapters.tezca.TezcaAdapter",
            return_value=mock_adapter,
        ):
            tool = ComplianceCheckTool()
            result = await tool.execute(domain="laboral")

        assert result.success
        assert "non-compliant" in result.output
        assert "Missing REPSE" in result.output
