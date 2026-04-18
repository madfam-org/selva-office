"""Telegram Bot API tools for agent-to-human channel + DM messaging.

Telegram is the fastest-provisioning rich-message channel we have: a bot
token grants immediate access, no SMS carrier approval, no webhook review.
Primary uses: ops alerts into a private group (pair with PagerDuty-style
pager), receipts + confirmations DMed to an individual user, light
interactivity via ``telegram_get_updates`` polling for inbound commands.

Uses the public Bot API (``api.telegram.org/bot<token>``). Credential:
``TELEGRAM_BOT_TOKEN``. All tools fail closed if the token is missing.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _creds_check() -> str | None:
    if not TELEGRAM_BOT_TOKEN:
        return "TELEGRAM_BOT_TOKEN must be set."
    return None


def _base() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def _call(
    method: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | str]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_base()}/{method}",
            headers={"Content-Type": "application/json"},
            json=payload or {},
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        # Telegram returns {"ok": false, "description": "..."}
        return body.get("description") or str(body)
    return f"HTTP {status}: {body}"


class TelegramSendMessageTool(BaseTool):
    """Send a text message to a Telegram chat."""

    name = "telegram_send_message"
    description = (
        "Send a text message to a Telegram chat (user DM, group, or "
        "channel). ``chat_id`` is the numeric ID from getUpdates (positive "
        "for users, negative for groups/channels) or a channel ``@handle``. "
        "``parse_mode`` is Markdown by default; set to empty string or "
        "'HTML' to switch. ``disable_preview`` suppresses URL previews "
        "(avoids noise on alert messages)."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": ["string", "integer"],
                    "description": "Numeric chat id or ``@channel_handle``.",
                },
                "text": {
                    "type": "string",
                    "description": "Message body. Max 4096 chars.",
                },
                "parse_mode": {
                    "type": "string",
                    "enum": ["Markdown", "MarkdownV2", "HTML", ""],
                    "default": "Markdown",
                },
                "disable_preview": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["chat_id", "text"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        parse_mode = kwargs.get("parse_mode", "Markdown")
        payload: dict[str, Any] = {
            "chat_id": kwargs["chat_id"],
            "text": kwargs["text"],
            "disable_web_page_preview": bool(kwargs.get("disable_preview", True)),
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            status, body = await _call("sendMessage", payload)
            if status >= 400 or not isinstance(body, dict) or not body.get("ok"):
                return ToolResult(success=False, error=_err(status, body))
            result = body.get("result") or {}
            return ToolResult(
                success=True,
                output=(
                    f"Telegram message sent to chat {kwargs['chat_id']} "
                    f"(message_id={result.get('message_id')})."
                ),
                data={
                    "message_id": result.get("message_id"),
                    "chat_id": (result.get("chat") or {}).get("id"),
                    "date": result.get("date"),
                },
            )
        except Exception as e:
            logger.error("telegram_send_message failed: %s", e)
            return ToolResult(success=False, error=str(e))


class TelegramSendPhotoTool(BaseTool):
    """Send a photo (by URL) with optional caption."""

    name = "telegram_send_photo"
    description = (
        "Send a photo to a Telegram chat. ``photo_url`` must be "
        "publicly-fetchable by Telegram's servers. Supports ``caption`` up "
        "to 1024 chars with Markdown formatting."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "chat_id": {"type": ["string", "integer"]},
                "photo_url": {"type": "string"},
                "caption": {"type": "string"},
            },
            "required": ["chat_id", "photo_url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        payload: dict[str, Any] = {
            "chat_id": kwargs["chat_id"],
            "photo": kwargs["photo_url"],
        }
        if kwargs.get("caption"):
            payload["caption"] = kwargs["caption"]
            payload["parse_mode"] = "Markdown"
        try:
            status, body = await _call("sendPhoto", payload)
            if status >= 400 or not isinstance(body, dict) or not body.get("ok"):
                return ToolResult(success=False, error=_err(status, body))
            result = body.get("result") or {}
            return ToolResult(
                success=True,
                output=(
                    f"Telegram photo sent to chat {kwargs['chat_id']} "
                    f"(message_id={result.get('message_id')})."
                ),
                data={
                    "message_id": result.get("message_id"),
                    "chat_id": (result.get("chat") or {}).get("id"),
                },
            )
        except Exception as e:
            logger.error("telegram_send_photo failed: %s", e)
            return ToolResult(success=False, error=str(e))


class TelegramGetUpdatesTool(BaseTool):
    """Poll for incoming Telegram updates (messages, commands, callbacks)."""

    name = "telegram_get_updates"
    description = (
        "Poll for incoming Telegram updates. Use ``offset`` to acknowledge "
        "a previous batch — set to ``update_id + 1`` of the last processed "
        "update. Only works when the bot has no webhook set; for webhook "
        "deployments, incoming messages arrive via the webhook endpoint "
        "instead."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "offset": {
                    "type": "integer",
                    "description": "First update_id to return. Pass "
                    "``last_update_id + 1`` to ack the previous batch.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "maximum": 100,
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        payload: dict[str, Any] = {
            "limit": min(int(kwargs.get("limit", 10)), 100),
        }
        if "offset" in kwargs and kwargs["offset"] is not None:
            payload["offset"] = int(kwargs["offset"])
        try:
            status, body = await _call("getUpdates", payload)
            if status >= 400 or not isinstance(body, dict) or not body.get("ok"):
                return ToolResult(success=False, error=_err(status, body))
            updates = body.get("result") or []
            summary = []
            for u in updates:
                msg = u.get("message") or u.get("edited_message") or {}
                summary.append(
                    {
                        "update_id": u.get("update_id"),
                        "chat_id": (msg.get("chat") or {}).get("id"),
                        "from": (msg.get("from") or {}).get("username")
                        or (msg.get("from") or {}).get("id"),
                        "text": (msg.get("text") or "")[:500],
                        "date": msg.get("date"),
                    }
                )
            return ToolResult(
                success=True,
                output=f"Fetched {len(summary)} update(s).",
                data={"updates": summary},
            )
        except Exception as e:
            logger.error("telegram_get_updates failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_telegram_tools() -> list[BaseTool]:
    """Return the Telegram tool set."""
    return [
        TelegramSendMessageTool(),
        TelegramSendPhotoTool(),
        TelegramGetUpdatesTool(),
    ]
