"""Image analysis tool using vision-capable LLM inference."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class ImageAnalysisTool(BaseTool):
    """Analyze an image using a vision-capable LLM and return a text description or answer.

    The tool constructs a multimodal message with the image content and a prompt,
    then returns it for the caller (worker graph node) to send through the
    inference router.  The ``requires_inference`` flag signals that the result
    contains messages that must be dispatched to an LLM.
    """

    name = "image_analysis"
    description = (
        "Analyze an image using a vision-capable LLM and return a text "
        "description or answer to a question about the image"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image data",
                },
                "image_url": {
                    "type": "string",
                    "description": "URL of the image to analyze",
                },
                "mime_type": {
                    "type": "string",
                    "description": (
                        "MIME type of the image (e.g., image/png, image/jpeg)"
                    ),
                    "default": "image/png",
                },
                "prompt": {
                    "type": "string",
                    "description": "Question or instruction for the image analysis",
                    "default": "Describe this image in detail.",
                },
            },
            "oneOf": [
                {"required": ["image_base64"]},
                {"required": ["image_url"]},
            ],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        image_base64: str | None = kwargs.get("image_base64")
        image_url: str | None = kwargs.get("image_url")
        mime_type: str = kwargs.get("mime_type", "image/png")
        prompt: str = kwargs.get("prompt", "Describe this image in detail.")

        if not image_base64 and not image_url:
            return ToolResult(
                success=False,
                error="Either image_base64 or image_url must be provided",
            )

        # Build multimodal content blocks
        content_blocks: list[dict[str, Any]] = [
            {"type": "text", "content": prompt},
        ]
        if image_base64:
            content_blocks.append({
                "type": "image_base64",
                "content": image_base64,
                "mime_type": mime_type,
            })
        elif image_url:
            content_blocks.append({
                "type": "image_url",
                "content": image_url,
            })

        # Return the constructed message -- the caller (worker graph node)
        # sends this through the inference router.
        return ToolResult(
            success=True,
            output=prompt,
            data={
                "messages": [{"role": "user", "content": content_blocks}],
                "requires_inference": True,
                "prompt": prompt,
            },
        )
