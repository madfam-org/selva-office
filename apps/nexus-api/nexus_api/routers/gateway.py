from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, Request

from ..config import get_settings
from ..memory_store.db import memory_store
from ..tasks.acp_tasks import run_acp_workflow_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gateway", tags=["Gateway"])


def _verify_hmac(body: bytes, signature: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 verification for incoming webhook payloads."""
    if not secret:
        return True  # Secret not configured — allow (warn in RUNBOOK to always set)
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
) -> Dict[str, Any]:
    """
    Hermes-style multi-channel gateway — Telegram.

    Validates the ``X-Telegram-Bot-Api-Secret-Token`` header (set when
    registering the webhook via ``setWebhook?secret_token=...``) and routes
    the ``/initiate_acp <url>`` slash command to a Celery ACP task.
    """
    settings = get_settings()
    body = await request.body()

    if settings.telegram_webhook_secret:
        if not x_telegram_bot_api_secret_token:
            raise HTTPException(status_code=401, detail="Missing Telegram secret token header")
        if not hmac.compare_digest(
            settings.telegram_webhook_secret,
            x_telegram_bot_api_secret_token,
        ):
            raise HTTPException(status_code=401, detail="Invalid Telegram secret token")

    payload = await request.json() if not body else __import__("json").loads(body)
    message = payload.get("message", {})
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id", "unknown")

    if text.startswith("/initiate_acp"):
        parts = text.split()
        if len(parts) > 1:
            target_url = parts[1]
            task = run_acp_workflow_task.delay(target_url)
            memory_store.insert_transcript(
                run_id=task.id,
                agent_role="gateway-telegram",
                role="user",
                content=f"ACP triggered from Telegram chat {chat_id} for {target_url}",
            )
            logger.info("Gateway (Telegram): ACP triggered for %s → task %s", target_url, task.id)
            return {"status": "success", "action": "acp_triggered", "task_id": task.id}

    return {"status": "ignored", "text": text}


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

@router.post("/discord/webhook")
async def discord_webhook(
    request: Request,
    x_signature_256: str = Header(None),
) -> Dict[str, Any]:
    """
    Hermes-style multi-channel gateway — Discord.

    Validates HMAC-SHA256 signature and handles:
    - ``/status``: returns recent swarm transcript hits from EdgeMemoryDB.
    - ``/initiate_acp <url>``: same trigger as Telegram.
    """
    settings = get_settings()
    body = await request.body()

    if settings.discord_webhook_secret:
        if not x_signature_256:
            raise HTTPException(status_code=401, detail="Missing X-Signature-256 header")
        if not _verify_hmac(body, x_signature_256, settings.discord_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid Discord webhook signature")

    payload = __import__("json").loads(body)
    content = payload.get("content", "").strip()

    if content.startswith("/status"):
        query = content.removeprefix("/status").strip() or "acp"
        hits = memory_store.fts_search(query, limit=5)
        return {
            "status": "success",
            "query": query,
            "results": hits,
        }

    if content.startswith("/initiate_acp"):
        parts = content.split()
        if len(parts) > 1:
            target_url = parts[1]
            task = run_acp_workflow_task.delay(target_url)
            memory_store.insert_transcript(
                run_id=task.id,
                agent_role="gateway-discord",
                role="user",
                content=f"ACP triggered from Discord for {target_url}",
            )
            logger.info("Gateway (Discord): ACP triggered for %s → task %s", target_url, task.id)
            return {"status": "success", "action": "acp_triggered", "task_id": task.id}

    return {"status": "ignored", "content": content}

