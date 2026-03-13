"""Artifact management tool (Phase 5.3 placeholder, used by tool registry now)."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class SaveArtifactTool(BaseTool):
    name = "save_artifact"
    description = "Save a task output artifact for later retrieval"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Artifact name"},
                "content": {"type": "string", "description": "Artifact content"},
                "content_type": {
                    "type": "string",
                    "default": "text/plain",
                    "description": "MIME type",
                },
            },
            "required": ["name", "content"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs.get("name", "")
        content = kwargs.get("content", "")
        content_type = kwargs.get("content_type", "text/plain")

        # In Phase 5.3, this will persist to S3/local FS + DB
        return ToolResult(
            output=f"Artifact '{name}' saved ({len(content)} chars, {content_type})",
            data={
                "artifact_name": name,
                "content_type": content_type,
                "size": len(content),
            },
        )
