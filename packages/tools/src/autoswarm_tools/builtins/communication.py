"""Communication tools: notifications and reports."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger("autoswarm.notifications")


class SendNotificationTool(BaseTool):
    name = "send_notification"
    description = "Send a notification via email, webhook, or log"

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
                "subject": {"type": "string", "default": "AutoSwarm Notification"},
                "webhook_url": {"type": "string", "default": ""},
            },
            "required": ["message"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        message = kwargs.get("message", "")
        channel = kwargs.get("channel", "log")
        recipient = kwargs.get("recipient", "")
        subject = kwargs.get("subject", "AutoSwarm Notification")
        webhook_url = kwargs.get("webhook_url", "")

        if channel == "email":
            return await self._send_email(recipient, subject, message)
        elif channel == "webhook":
            return await self._send_webhook(webhook_url, message)
        else:
            logger.info("Notification [log] to=%s: %s", recipient or "broadcast", message)
            return ToolResult(
                output=f"Notification logged: {message[:100]}",
                data={"channel": "log", "recipient": recipient, "message": message},
            )

    async def _send_email(self, to: str, subject: str, body: str) -> ToolResult:
        api_key = os.environ.get("RESEND_API_KEY")
        from_addr = os.environ.get("EMAIL_FROM", "AutoSwarm <noreply@selva.town>")

        if not api_key:
            logger.warning("RESEND_API_KEY not configured — email logged only")
            return ToolResult(output="Email skipped (no API key)", data={"sent": False})

        if not to:
            return ToolResult(output="Email skipped (no recipient)", data={"sent": False})

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"from": from_addr, "to": [to], "subject": subject, "html": body},
            )

        if resp.status_code in (200, 201):
            email_id = resp.json().get("id", "unknown")
            logger.info("Email sent to=%s id=%s", to, email_id)
            return ToolResult(output=f"Email sent to {to}", data={"sent": True, "id": email_id})

        logger.error("Email failed: %s %s", resp.status_code, resp.text[:200])
        return ToolResult(output=f"Email failed: {resp.status_code}", data={"sent": False})

    async def _send_webhook(self, url: str, message: str) -> ToolResult:
        target = url or os.environ.get("NOTIFICATION_WEBHOOK_URL", "")
        if not target:
            logger.warning("No webhook URL — notification logged only")
            return ToolResult(output="Webhook skipped (no URL)", data={"sent": False})

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(target, json={"text": message})

        if resp.status_code < 300:
            logger.info("Webhook delivered to %s", target[:50])
            return ToolResult(output=f"Webhook sent to {target[:50]}", data={"sent": True})

        logger.error("Webhook failed: %s", resp.status_code)
        return ToolResult(output=f"Webhook failed: {resp.status_code}", data={"sent": False})


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
