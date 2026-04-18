"""Discord webhook tools for agent-to-human + agent-to-channel messaging.

Covers the zero-friction path: ops + community channels frequently route
through Discord webhooks because they require no bot token and no OAuth
flow. Every channel in the MADFAM community server exposes one or more
webhooks and agents need to post into them for alerts, build notifications,
and incident summaries without escalating to a shared bot identity.

For richer bot interactions (slash commands, member DMs, read access) a
full bot token is required; this module deliberately stops at webhooks so
the surface stays minimal + auditable. Default webhook comes from
``DISCORD_WEBHOOK_URL``; every tool accepts a per-call ``webhook_url``
override so agents can fan out to multiple channels from one call site.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")


def _resolve_webhook(webhook_url: str | None) -> str | None:
    """Pick the explicit override if present, else the env default."""
    return (webhook_url or "").strip() or DEFAULT_WEBHOOK or None


async def _post(webhook: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            webhook,
            headers={"Content-Type": "application/json"},
            json=payload,
            # Use ?wait=true so Discord returns the created message body,
            # giving us the message_id downstream jobs can reference.
            params={"wait": "true"},
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("message") or str(body)
    return f"HTTP {status}: {body}"


class DiscordSendMessageTool(BaseTool):
    """Post a message to a Discord channel via its incoming webhook."""

    name = "discord_send_message"
    description = (
        "Post a message to a Discord channel. ``webhook_url`` is optional "
        "when ``DISCORD_WEBHOOK_URL`` env var is set. ``username`` overrides "
        "the webhook's configured bot name for this message only. Pass "
        "``embeds`` (Discord embed objects) for rich-formatted alerts."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "webhook_url": {
                    "type": "string",
                    "description": "Full webhook URL, e.g. "
                    "https://discord.com/api/webhooks/<id>/<token>. "
                    "Falls back to DISCORD_WEBHOOK_URL.",
                },
                "content": {
                    "type": "string",
                    "description": "Message text. Max 2000 chars. Supports "
                    "Discord markdown (`**bold**`, `` `inline code` ``, "
                    "``` ```code blocks``` ```).",
                },
                "username": {"type": "string"},
                "embeds": {
                    "type": "array",
                    "items": {"type": "object"},
                    "default": [],
                    "description": "Discord embed objects "
                    "(title, description, fields, color, footer...).",
                },
            },
            "required": ["content"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        webhook = _resolve_webhook(kwargs.get("webhook_url"))
        if not webhook:
            return ToolResult(
                success=False,
                error="webhook_url required (or set DISCORD_WEBHOOK_URL).",
            )
        payload: dict[str, Any] = {"content": kwargs["content"]}
        if kwargs.get("username"):
            payload["username"] = kwargs["username"]
        embeds = kwargs.get("embeds") or []
        if embeds:
            payload["embeds"] = embeds
        try:
            status, body = await _post(webhook, payload)
            if status >= 400:
                return ToolResult(success=False, error=_err(status, body))
            msg_id = body.get("id") if isinstance(body, dict) else None
            return ToolResult(
                success=True,
                output=f"Discord message sent (id={msg_id}).",
                data={"message_id": msg_id},
            )
        except Exception as e:
            logger.error("discord_send_message failed: %s", e)
            return ToolResult(success=False, error=str(e))


class DiscordSendEmbedTool(BaseTool):
    """Convenience: build + post a single rich embed."""

    name = "discord_send_embed"
    description = (
        "Post a single rich embed to a Discord channel. Convenience wrapper "
        "around discord_send_message that builds the embed object for you. "
        "``color`` is an integer (decimal) — e.g. 0x00ff00 = 65280 for green. "
        "``fields`` is a list of ``{name, value, inline?}`` dicts."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "color": {
                    "type": "integer",
                    "description": "Embed side-bar color, decimal int "
                    "(0..16777215). Common: 3066993 green, 15158332 red, "
                    "15844367 amber, 3447003 blue.",
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "object"},
                    "default": [],
                },
            },
            "required": ["title", "description"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        webhook = _resolve_webhook(kwargs.get("webhook_url"))
        if not webhook:
            return ToolResult(
                success=False,
                error="webhook_url required (or set DISCORD_WEBHOOK_URL).",
            )
        embed: dict[str, Any] = {
            "title": kwargs["title"],
            "description": kwargs["description"],
        }
        if "color" in kwargs and kwargs["color"] is not None:
            embed["color"] = int(kwargs["color"])
        fields = kwargs.get("fields") or []
        if fields:
            embed["fields"] = fields
        payload = {"embeds": [embed]}
        try:
            status, body = await _post(webhook, payload)
            if status >= 400:
                return ToolResult(success=False, error=_err(status, body))
            msg_id = body.get("id") if isinstance(body, dict) else None
            return ToolResult(
                success=True,
                output=f"Discord embed sent (id={msg_id}).",
                data={"message_id": msg_id, "title": kwargs["title"]},
            )
        except Exception as e:
            logger.error("discord_send_embed failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_discord_tools() -> list[BaseTool]:
    """Return the Discord tool set."""
    return [
        DiscordSendMessageTool(),
        DiscordSendEmbedTool(),
    ]
