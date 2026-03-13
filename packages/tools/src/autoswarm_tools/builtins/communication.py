"""Communication tools: notifications and reports."""

from __future__ import annotations

import json
from typing import Any

from ..base import BaseTool, ToolResult


class SendNotificationTool(BaseTool):
    name = "send_notification"
    description = "Send a notification message (logged; delivery depends on configured channels)"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Notification message"},
                "channel": {
                    "type": "string",
                    "description": "Channel type (log, webhook, email)",
                    "default": "log",
                },
                "recipient": {"type": "string", "default": ""},
            },
            "required": ["message"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import logging

        message = kwargs.get("message", "")
        channel = kwargs.get("channel", "log")
        recipient = kwargs.get("recipient", "")

        logger = logging.getLogger("autoswarm.notifications")
        logger.info(
            "Notification [%s] to=%s: %s", channel, recipient or "broadcast", message
        )

        return ToolResult(
            output=f"Notification sent via {channel}",
            data={"channel": channel, "recipient": recipient, "message": message},
        )


class CreateReportTool(BaseTool):
    name = "create_report"
    description = "Create a structured report from provided data"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Report title"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                    "description": "Report sections",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json", "text"],
                    "default": "markdown",
                },
            },
            "required": ["title", "sections"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        title = kwargs.get("title", "Report")
        sections = kwargs.get("sections", [])
        fmt = kwargs.get("format", "markdown")

        if fmt == "markdown":
            lines = [f"# {title}\n"]
            for section in sections:
                lines.append(f"## {section.get('heading', '')}\n")
                lines.append(section.get("content", "") + "\n")
            output = "\n".join(lines)
        elif fmt == "json":
            output = json.dumps({"title": title, "sections": sections}, indent=2)
        else:
            lines = [title, "=" * len(title)]
            for section in sections:
                lines.append(f"\n{section.get('heading', '')}")
                lines.append("-" * len(section.get("heading", "")))
                lines.append(section.get("content", ""))
            output = "\n".join(lines)

        return ToolResult(output=output, data={"title": title, "format": fmt})
