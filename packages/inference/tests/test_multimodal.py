"""Tests for multimodal inference support.

Covers ContentType/MediaContent models, has_media() detection,
provider-specific message formatting, and router vision filtering.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from madfam_inference.base import InferenceProvider
from madfam_inference.providers.anthropic import AnthropicProvider
from madfam_inference.providers.ollama import OllamaProvider
from madfam_inference.providers.openai import OpenAIProvider
from madfam_inference.router import ModelRouter
from madfam_inference.types import (
    ContentType,
    InferenceRequest,
    InferenceResponse,
    MediaContent,
    RoutingPolicy,
    Sensitivity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_only_request() -> InferenceRequest:
    """Build a simple text-only inference request."""
    return InferenceRequest(
        messages=[{"role": "user", "content": "Hello, world!"}],
    )


def _multimodal_request(
    *,
    image_type: str = "image_base64",
    image_content: str = "aW1hZ2VkYXRh",
    mime_type: str = "image/png",
) -> InferenceRequest:
    """Build an inference request with an image content block."""
    content_blocks: list[dict[str, Any]] = [
        {"type": "text", "content": "What is in this image?"},
    ]
    block: dict[str, Any] = {"type": image_type, "content": image_content}
    if image_type == "image_base64":
        block["mime_type"] = mime_type
    content_blocks.append(block)

    return InferenceRequest(
        messages=[{"role": "user", "content": content_blocks}],
    )


class _VisionProvider(InferenceProvider):
    """Mock provider that supports vision."""

    def __init__(self, provider_name: str) -> None:
        self.name = provider_name
        self._vision = True

    @property
    def supports_vision(self) -> bool:
        return self._vision

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(
            content="vision response",
            model="vision-model",
            provider=self.name,
            usage={"input_tokens": 10, "output_tokens": 20},
        )

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        yield "chunk"

    async def list_models(self) -> list[str]:
        return ["vision-model"]


class _TextOnlyProvider(InferenceProvider):
    """Mock provider that does NOT support vision."""

    def __init__(self, provider_name: str) -> None:
        self.name = provider_name

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(
            content="text response",
            model="text-model",
            provider=self.name,
            usage={"input_tokens": 5, "output_tokens": 10},
        )

    async def stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        yield "text chunk"

    async def list_models(self) -> list[str]:
        return ["text-model"]


# ---------------------------------------------------------------------------
# ContentType and MediaContent model tests
# ---------------------------------------------------------------------------

class TestContentType:
    def test_enum_values(self) -> None:
        assert ContentType.TEXT == "text"
        assert ContentType.IMAGE_URL == "image_url"
        assert ContentType.IMAGE_BASE64 == "image_base64"

    def test_enum_members(self) -> None:
        assert set(ContentType) == {
            ContentType.TEXT,
            ContentType.IMAGE_URL,
            ContentType.IMAGE_BASE64,
        }


class TestMediaContent:
    def test_text_block(self) -> None:
        block = MediaContent(type=ContentType.TEXT, content="hello")
        assert block.type == ContentType.TEXT
        assert block.content == "hello"
        assert block.mime_type is None

    def test_image_base64_block(self) -> None:
        block = MediaContent(
            type=ContentType.IMAGE_BASE64,
            content="aW1hZ2VkYXRh",
            mime_type="image/png",
        )
        assert block.type == ContentType.IMAGE_BASE64
        assert block.content == "aW1hZ2VkYXRh"
        assert block.mime_type == "image/png"

    def test_image_url_block(self) -> None:
        block = MediaContent(
            type=ContentType.IMAGE_URL,
            content="https://example.com/image.png",
        )
        assert block.type == ContentType.IMAGE_URL
        assert block.content == "https://example.com/image.png"


# ---------------------------------------------------------------------------
# InferenceRequest.has_media() tests
# ---------------------------------------------------------------------------

class TestHasMedia:
    def test_text_only_returns_false(self) -> None:
        request = _text_only_request()
        assert request.has_media() is False

    def test_empty_messages_returns_false(self) -> None:
        request = InferenceRequest(messages=[])
        assert request.has_media() is False

    def test_string_content_returns_false(self) -> None:
        request = InferenceRequest(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi there"},
            ],
        )
        assert request.has_media() is False

    def test_image_base64_returns_true(self) -> None:
        request = _multimodal_request(image_type="image_base64")
        assert request.has_media() is True

    def test_image_url_returns_true(self) -> None:
        request = _multimodal_request(
            image_type="image_url",
            image_content="https://example.com/img.png",
        )
        assert request.has_media() is True

    def test_text_blocks_only_returns_false(self) -> None:
        """A list of content blocks that are all text should return False."""
        request = InferenceRequest(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "content": "part one"},
                    {"type": "text", "content": "part two"},
                ],
            }],
        )
        assert request.has_media() is False

    def test_mixed_messages_returns_true(self) -> None:
        """If any message in the list has media, has_media returns True."""
        request = InferenceRequest(
            messages=[
                {"role": "user", "content": "text only"},
                {"role": "user", "content": [
                    {"type": "text", "content": "look at this"},
                    {"type": "image_base64", "content": "abc", "mime_type": "image/png"},
                ]},
            ],
        )
        assert request.has_media() is True


# ---------------------------------------------------------------------------
# OpenAI provider _format_messages tests
# ---------------------------------------------------------------------------

class TestOpenAIFormatMessages:
    def test_string_content_passthrough(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hello"},
        ]
        result = OpenAIProvider._format_messages(messages)
        assert result == [{"role": "user", "content": "hello"}]

    def test_text_block_conversion(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "text", "content": "describe this"},
            ]},
        ]
        result = OpenAIProvider._format_messages(messages)
        assert len(result) == 1
        content = result[0]["content"]
        assert len(content) == 1
        assert content[0] == {"type": "text", "text": "describe this"}

    def test_image_url_conversion(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "image_url", "content": "https://example.com/img.png"},
            ]},
        ]
        result = OpenAIProvider._format_messages(messages)
        block = result[0]["content"][0]
        assert block["type"] == "image_url"
        assert block["image_url"]["url"] == "https://example.com/img.png"

    def test_image_base64_to_data_uri(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {
                    "type": "image_base64",
                    "content": "aW1hZ2VkYXRh",
                    "mime_type": "image/jpeg",
                },
            ]},
        ]
        result = OpenAIProvider._format_messages(messages)
        block = result[0]["content"][0]
        assert block["type"] == "image_url"
        assert block["image_url"]["url"] == "data:image/jpeg;base64,aW1hZ2VkYXRh"

    def test_image_base64_default_mime_type(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "image_base64", "content": "abc123"},
            ]},
        ]
        result = OpenAIProvider._format_messages(messages)
        block = result[0]["content"][0]
        assert block["image_url"]["url"].startswith("data:image/png;base64,")

    def test_mixed_content_blocks(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "text", "content": "What is this?"},
                {
                    "type": "image_base64",
                    "content": "base64data",
                    "mime_type": "image/png",
                },
            ]},
        ]
        result = OpenAIProvider._format_messages(messages)
        content = result[0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"

    def test_preserves_role(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "assistant", "content": [
                {"type": "text", "content": "I see an image."},
            ]},
        ]
        result = OpenAIProvider._format_messages(messages)
        assert result[0]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Anthropic provider _format_messages tests
# ---------------------------------------------------------------------------

class TestAnthropicFormatMessages:
    def test_string_content_wrapped(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hello"},
        ]
        result = AnthropicProvider._format_messages(messages)
        content = result[0]["content"]
        assert content == [{"type": "text", "text": "hello"}]

    def test_text_block(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "text", "content": "describe"},
            ]},
        ]
        result = AnthropicProvider._format_messages(messages)
        block = result[0]["content"][0]
        assert block == {"type": "text", "text": "describe"}

    def test_image_base64_block(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {
                    "type": "image_base64",
                    "content": "aW1hZ2VkYXRh",
                    "mime_type": "image/jpeg",
                },
            ]},
        ]
        result = AnthropicProvider._format_messages(messages)
        block = result[0]["content"][0]
        assert block["type"] == "image"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "image/jpeg"
        assert block["source"]["data"] == "aW1hZ2VkYXRh"

    def test_image_url_block(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "image_url", "content": "https://example.com/img.png"},
            ]},
        ]
        result = AnthropicProvider._format_messages(messages)
        block = result[0]["content"][0]
        assert block["type"] == "image"
        assert block["source"]["type"] == "url"
        assert block["source"]["url"] == "https://example.com/img.png"

    def test_mixed_content(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "text", "content": "What is this?"},
                {
                    "type": "image_base64",
                    "content": "data",
                    "mime_type": "image/png",
                },
            ]},
        ]
        result = AnthropicProvider._format_messages(messages)
        content = result[0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image"

    def test_none_content_handled(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "assistant", "content": None},
        ]
        result = AnthropicProvider._format_messages(messages)
        content = result[0]["content"]
        assert content == [{"type": "text", "text": ""}]


# ---------------------------------------------------------------------------
# Ollama provider _format_messages tests
# ---------------------------------------------------------------------------

class TestOllamaFormatMessages:
    def test_string_content_passthrough(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hello"},
        ]
        result = OllamaProvider._format_messages(messages)
        assert result == [{"role": "user", "content": "hello"}]

    def test_image_base64_extracted_to_images_field(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "text", "content": "What is this?"},
                {
                    "type": "image_base64",
                    "content": "aW1hZ2VkYXRh",
                    "mime_type": "image/png",
                },
            ]},
        ]
        result = OllamaProvider._format_messages(messages)
        assert len(result) == 1
        assert result[0]["content"] == "What is this?"
        assert result[0]["images"] == ["aW1hZ2VkYXRh"]

    def test_multiple_images(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "text", "content": "Compare these"},
                {"type": "image_base64", "content": "img1", "mime_type": "image/png"},
                {"type": "image_base64", "content": "img2", "mime_type": "image/jpeg"},
            ]},
        ]
        result = OllamaProvider._format_messages(messages)
        assert result[0]["images"] == ["img1", "img2"]

    def test_image_url_fallback_to_text(self) -> None:
        """Ollama does not support image URLs natively -- they are included as text."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "image_url", "content": "https://example.com/img.png"},
            ]},
        ]
        result = OllamaProvider._format_messages(messages)
        assert "https://example.com/img.png" in result[0]["content"]
        assert "images" not in result[0]

    def test_no_images_key_for_text_only_blocks(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [
                {"type": "text", "content": "just text"},
            ]},
        ]
        result = OllamaProvider._format_messages(messages)
        assert result[0]["content"] == "just text"
        assert "images" not in result[0]


# ---------------------------------------------------------------------------
# Provider supports_vision property tests
# ---------------------------------------------------------------------------

class TestSupportsVision:
    def test_base_provider_defaults_false(self) -> None:
        provider = _TextOnlyProvider("test")
        assert provider.supports_vision is False

    def test_openai_supports_vision(self) -> None:
        provider = OpenAIProvider(api_key="test")
        assert provider.supports_vision is True

    def test_anthropic_supports_vision(self) -> None:
        provider = AnthropicProvider(api_key="test")
        assert provider.supports_vision is True

    def test_ollama_supports_vision(self) -> None:
        provider = OllamaProvider()
        assert provider.supports_vision is True

    def test_generic_vision_default_true(self) -> None:
        from madfam_inference.providers.generic import GenericOpenAIProvider

        provider = GenericOpenAIProvider(
            base_url="http://localhost:8000/v1",
            model="test",
        )
        assert provider.supports_vision is True

    def test_generic_vision_disabled(self) -> None:
        from madfam_inference.providers.generic import GenericOpenAIProvider

        provider = GenericOpenAIProvider(
            base_url="http://localhost:8000/v1",
            model="test",
            vision=False,
        )
        assert provider.supports_vision is False


# ---------------------------------------------------------------------------
# Router vision filtering tests
# ---------------------------------------------------------------------------

class TestRouterVisionFiltering:
    async def test_multimodal_request_selects_vision_provider(self) -> None:
        """When a request has media, the router should prefer vision providers."""
        providers: dict[str, InferenceProvider] = {
            "text_only": _TextOnlyProvider("text_only"),
            "anthropic": _VisionProvider("anthropic"),
        }
        router = ModelRouter(providers=providers)
        request = _multimodal_request()
        response = await router.complete(request)
        assert response.provider == "anthropic"

    async def test_multimodal_request_filters_non_vision(self) -> None:
        """Non-vision providers are excluded when media is present."""
        providers: dict[str, InferenceProvider] = {
            "openai": _VisionProvider("openai"),
            "cheapo": _TextOnlyProvider("cheapo"),
        }
        router = ModelRouter(providers=providers)
        request = _multimodal_request()
        # Even though cheapo might be in candidates, vision filtering
        # should narrow to openai only
        response = await router.complete(request)
        assert response.provider == "openai"

    async def test_text_request_does_not_filter(self) -> None:
        """Text-only requests should not apply vision filtering."""
        providers: dict[str, InferenceProvider] = {
            "deepinfra": _TextOnlyProvider("deepinfra"),
            "anthropic": _VisionProvider("anthropic"),
        }
        router = ModelRouter(providers=providers)
        request = _text_only_request()
        request.policy = RoutingPolicy(sensitivity=Sensitivity.PUBLIC)
        response = await router.complete(request)
        # PUBLIC prefers cheapest (deepinfra) -- no vision filtering
        assert response.provider == "deepinfra"

    async def test_fallback_when_no_vision_providers(self) -> None:
        """If no vision providers exist, fall through to all candidates."""
        providers: dict[str, InferenceProvider] = {
            "anthropic": _TextOnlyProvider("anthropic"),
        }
        router = ModelRouter(providers=providers)
        request = _multimodal_request()
        # Should still work -- falls through since vision_candidates is empty
        response = await router.complete(request)
        assert response.provider == "anthropic"

    async def test_vision_filtering_respects_sensitivity(self) -> None:
        """Vision filtering works within the sensitivity-restricted candidate set."""
        providers: dict[str, InferenceProvider] = {
            "ollama": _VisionProvider("ollama"),
            "anthropic": _VisionProvider("anthropic"),
        }
        router = ModelRouter(providers=providers)
        request = _multimodal_request()
        request.policy = RoutingPolicy(sensitivity=Sensitivity.RESTRICTED)
        response = await router.complete(request)
        # Restricted -> only ollama is a candidate, and it supports vision
        assert response.provider == "ollama"

    async def test_multiple_vision_providers_uses_priority(self) -> None:
        """Among multiple vision providers, the original priority order is kept."""
        providers: dict[str, InferenceProvider] = {
            "anthropic": _VisionProvider("anthropic"),
            "openai": _VisionProvider("openai"),
        }
        router = ModelRouter(providers=providers)
        request = _multimodal_request()
        request.policy = RoutingPolicy(sensitivity=Sensitivity.INTERNAL)
        response = await router.complete(request)
        # INTERNAL priority: anthropic > openai
        assert response.provider == "anthropic"
