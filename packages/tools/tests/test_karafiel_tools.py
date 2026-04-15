"""Tests for Karafiel compliance tools."""

from __future__ import annotations

import pytest

from autoswarm_tools.builtins.karafiel import (
    BlacklistCheckTool,
    CFDIGenerateTool,
    CFDIStampTool,
    CFDIStatusTool,
    RFCValidationTool,
)

KARAFIEL_TOOLS = [
    ("rfc_validation", RFCValidationTool),
    ("cfdi_generate", CFDIGenerateTool),
    ("cfdi_stamp", CFDIStampTool),
    ("cfdi_status", CFDIStatusTool),
    ("blacklist_check", BlacklistCheckTool),
]


class TestKarafielToolsSchema:
    """All Karafiel tools have valid schemas and metadata."""

    @pytest.mark.parametrize("expected_name,tool_cls", KARAFIEL_TOOLS)
    def test_tool_name(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert tool.name == expected_name

    @pytest.mark.parametrize("expected_name,tool_cls", KARAFIEL_TOOLS)
    def test_tool_has_description(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        assert len(tool.description) > 10

    @pytest.mark.parametrize("expected_name,tool_cls", KARAFIEL_TOOLS)
    def test_tool_schema_is_valid_json_schema(
        self, expected_name: str, tool_cls: type
    ) -> None:
        tool = tool_cls()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert len(schema["required"]) >= 1

    @pytest.mark.parametrize("expected_name,tool_cls", KARAFIEL_TOOLS)
    def test_tool_openai_spec(self, expected_name: str, tool_cls: type) -> None:
        tool = tool_cls()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == expected_name


class TestKarafielToolsInRegistry:
    """Karafiel tools are registered in get_builtin_tools()."""

    def test_all_karafiel_tools_in_registry(self) -> None:
        from autoswarm_tools.builtins import get_builtin_tools

        tools = get_builtin_tools()
        names = {t.name for t in tools}
        for expected_name, _ in KARAFIEL_TOOLS:
            assert expected_name in names, f"{expected_name} missing from registry"


class TestKarafielToolsMissingInput:
    """Tools return errors on missing required inputs."""

    @pytest.mark.asyncio
    async def test_rfc_validation_missing_rfc(self) -> None:
        tool = RFCValidationTool()
        result = await tool.execute()
        assert not result.success
        assert "rfc" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_cfdi_generate_missing_fields(self) -> None:
        tool = CFDIGenerateTool()
        result = await tool.execute(emisor_rfc="AAA")
        assert not result.success

    @pytest.mark.asyncio
    async def test_cfdi_stamp_missing_xml(self) -> None:
        tool = CFDIStampTool()
        result = await tool.execute()
        assert not result.success

    @pytest.mark.asyncio
    async def test_cfdi_status_missing_uuid(self) -> None:
        tool = CFDIStatusTool()
        result = await tool.execute()
        assert not result.success

    @pytest.mark.asyncio
    async def test_blacklist_check_missing_rfc(self) -> None:
        tool = BlacklistCheckTool()
        result = await tool.execute()
        assert not result.success
