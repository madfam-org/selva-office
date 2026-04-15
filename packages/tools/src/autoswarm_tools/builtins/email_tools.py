"""Email tools: send via Resend API, read via IMAP (placeholder)."""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger("autoswarm.email")


class SendEmailTool(BaseTool):
    name = "send_email"
    description = (
        "Send an email via the Resend API. "
        "Requires RESEND_API_KEY env var. "
        "Supports HTML body content."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "html": {
                    "type": "string",
                    "description": "HTML body content",
                },
                "from_address": {
                    "type": "string",
                    "description": "Sender address (defaults to EMAIL_FROM env var)",
                    "default": "",
                },
            },
            "required": ["to", "subject", "html"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import httpx

        to = kwargs.get("to", "")
        subject = kwargs.get("subject", "")
        html = kwargs.get("html", "")
        from_address = kwargs.get("from_address", "") or os.environ.get(
            "EMAIL_FROM", "AutoSwarm <noreply@selva.town>"
        )

        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            logger.warning("RESEND_API_KEY not configured")
            return ToolResult(
                success=False,
                error="RESEND_API_KEY not configured",
            )

        if not to:
            return ToolResult(success=False, error="Recipient 'to' is required")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "from": from_address,
                        "to": [to],
                        "subject": subject,
                        "html": html,
                    },
                )

            if resp.status_code in (200, 201):
                message_id = resp.json().get("id", "unknown")
                logger.info("Email sent to=%s id=%s", to, message_id)
                return ToolResult(
                    output=f"Email sent to {to} (id={message_id})",
                    data={"message_id": message_id, "to": to, "subject": subject},
                )

            logger.error("Email send failed: %s %s", resp.status_code, resp.text[:200])
            return ToolResult(
                success=False,
                error=f"Resend API error: {resp.status_code} {resp.text[:200]}",
            )
        except Exception as exc:
            logger.error("send_email failed: %s", exc)
            return ToolResult(success=False, error=str(exc))


class ReadEmailTool(BaseTool):
    name = "read_email"
    description = (
        "Read emails from a mailbox via IMAP. "
        "Currently a placeholder -- returns an error indicating "
        "IMAP is not configured. Production would use imaplib."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mailbox": {
                    "type": "string",
                    "description": "Mailbox folder to read (e.g. INBOX)",
                    "default": "INBOX",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of recent emails to retrieve",
                    "default": 10,
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=False,
            error="IMAP not configured. Set IMAP_HOST, IMAP_USER, IMAP_PASSWORD env vars.",
        )
