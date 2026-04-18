"""Tests for the tool registry."""

from __future__ import annotations

import pytest

from selva_tools.base import BaseTool, ToolResult
from selva_tools.registry import ToolRegistry


class MockTool(BaseTool):
    name = "mock_tool"
    description = "A mock tool for testing"

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"},
            },
            "required": ["input"],
        }

    async def execute(self, **kwargs) -> ToolResult:  # type: ignore[override]
        return ToolResult(output=f"Mock output: {kwargs.get('input', '')}")


class TestToolRegistry:
    def setup_method(self) -> None:
        # Reset singleton for test isolation
        ToolRegistry._instance = None
        self.registry = ToolRegistry()

    def test_register_and_get(self) -> None:
        tool = MockTool()
        self.registry.register(tool)
        assert self.registry.get("mock_tool") is tool

    def test_get_nonexistent(self) -> None:
        assert self.registry.get("nonexistent") is None

    def test_list_tools(self) -> None:
        self.registry.register(MockTool())
        assert "mock_tool" in self.registry.list_tools()

    def test_get_specs(self) -> None:
        self.registry.register(MockTool())
        specs = self.registry.get_specs(["mock_tool"])
        assert len(specs) == 1
        assert specs[0]["type"] == "function"
        assert specs[0]["function"]["name"] == "mock_tool"

    def test_get_all_specs(self) -> None:
        self.registry.register(MockTool())
        specs = self.registry.get_specs()
        assert len(specs) >= 1

    def test_openai_spec_format(self) -> None:
        tool = MockTool()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert "parameters" in spec["function"]
        assert spec["function"]["parameters"]["type"] == "object"

    def test_discover_builtins(self) -> None:
        self.registry.discover_builtins()
        tools = self.registry.list_tools()
        assert len(tools) >= 20
        assert "file_read" in tools
        assert "bash_exec" in tools
        assert "git_commit" in tools
        assert "web_search" in tools
        assert "json_parse" in tools

    def test_discover_builtins_idempotent(self) -> None:
        self.registry.discover_builtins()
        count1 = len(self.registry.list_tools())
        self.registry.discover_builtins()
        count2 = len(self.registry.list_tools())
        assert count1 == count2


class TestMockToolExecution:
    @pytest.mark.asyncio
    async def test_execute(self) -> None:
        tool = MockTool()
        result = await tool.execute(input="hello")
        assert result.success
        assert "hello" in result.output
