"""Tests for the ImageAnalysisTool."""

from __future__ import annotations

import pytest

from selva_tools.builtins import get_builtin_tools
from selva_tools.builtins.image_analysis import ImageAnalysisTool


class TestImageAnalysisToolMetadata:
    def test_name(self) -> None:
        tool = ImageAnalysisTool()
        assert tool.name == "image_analysis"

    def test_description(self) -> None:
        tool = ImageAnalysisTool()
        assert "image" in tool.description.lower()
        assert "vision" in tool.description.lower()

    def test_parameters_schema_is_valid(self) -> None:
        tool = ImageAnalysisTool()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "image_base64" in schema["properties"]
        assert "image_url" in schema["properties"]
        assert "mime_type" in schema["properties"]
        assert "prompt" in schema["properties"]
        # oneOf for image source requirement
        assert "oneOf" in schema
        assert len(schema["oneOf"]) == 2

    def test_openai_spec_format(self) -> None:
        tool = ImageAnalysisTool()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "image_analysis"
        assert "parameters" in spec["function"]
        assert "description" in spec["function"]


class TestImageAnalysisToolExecution:
    @pytest.mark.asyncio
    async def test_with_image_base64(self) -> None:
        tool = ImageAnalysisTool()
        result = await tool.execute(
            image_base64="aW1hZ2VkYXRh",
            mime_type="image/png",
            prompt="What is in this image?",
        )
        assert result.success
        assert result.data["requires_inference"] is True
        assert result.data["prompt"] == "What is in this image?"

        messages = result.data["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        content = messages[0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["content"] == "What is in this image?"
        assert content[1]["type"] == "image_base64"
        assert content[1]["content"] == "aW1hZ2VkYXRh"
        assert content[1]["mime_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_with_image_url(self) -> None:
        tool = ImageAnalysisTool()
        result = await tool.execute(
            image_url="https://example.com/photo.jpg",
            prompt="Describe this photo.",
        )
        assert result.success
        assert result.data["requires_inference"] is True

        messages = result.data["messages"]
        content = messages[0]["content"]
        assert len(content) == 2
        assert content[1]["type"] == "image_url"
        assert content[1]["content"] == "https://example.com/photo.jpg"

    @pytest.mark.asyncio
    async def test_default_prompt(self) -> None:
        tool = ImageAnalysisTool()
        result = await tool.execute(image_base64="abc123")
        assert result.success
        assert result.data["prompt"] == "Describe this image in detail."
        content = result.data["messages"][0]["content"]
        assert content[0]["content"] == "Describe this image in detail."

    @pytest.mark.asyncio
    async def test_default_mime_type(self) -> None:
        tool = ImageAnalysisTool()
        result = await tool.execute(image_base64="abc123")
        assert result.success
        content = result.data["messages"][0]["content"]
        assert content[1]["mime_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_neither_image_returns_error(self) -> None:
        tool = ImageAnalysisTool()
        result = await tool.execute(prompt="What do you see?")
        assert not result.success
        assert result.error is not None
        assert "image_base64" in result.error or "image_url" in result.error

    @pytest.mark.asyncio
    async def test_base64_preferred_over_url_when_both_provided(self) -> None:
        """When both are provided, image_base64 takes precedence."""
        tool = ImageAnalysisTool()
        result = await tool.execute(
            image_base64="base64data",
            image_url="https://example.com/img.png",
        )
        assert result.success
        content = result.data["messages"][0]["content"]
        # Should use base64, not URL
        image_block = content[1]
        assert image_block["type"] == "image_base64"


class TestImageAnalysisToolRegistration:
    def test_appears_in_builtin_tools(self) -> None:
        tools = get_builtin_tools()
        tool_names = [t.name for t in tools]
        assert "image_analysis" in tool_names

    def test_builtin_instance_type(self) -> None:
        tools = get_builtin_tools()
        image_tools = [t for t in tools if t.name == "image_analysis"]
        assert len(image_tools) == 1
        assert isinstance(image_tools[0], ImageAnalysisTool)
