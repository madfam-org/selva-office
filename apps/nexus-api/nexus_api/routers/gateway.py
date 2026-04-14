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


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

@router.post("/slack/webhook")
async def slack_webhook(
    request: Request,
    x_slack_signature: str = Header(None),
    x_slack_request_timestamp: str = Header(None),
) -> Dict[str, Any]:
    """
    Hermes-style multi-channel gateway — Slack.

    Validates Slack's v0 HMAC-SHA256 signature with timestamp replay protection
    (rejects requests older than 5 minutes), then routes slash commands.
    """
    import time as _time

    settings = get_settings()
    body = await request.body()

    if settings.slack_signing_secret:
        if not x_slack_signature or not x_slack_request_timestamp:
            raise HTTPException(status_code=401, detail="Missing Slack signature headers")

        # Replay protection: reject timestamps > 5 minutes old
        try:
            ts = int(x_slack_request_timestamp)
            if abs(_time.time() - ts) > 300:
                raise HTTPException(status_code=401, detail="Slack request timestamp too old")
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid Slack timestamp")

        sig_base = f"v0:{x_slack_request_timestamp}:{body.decode()}"
        expected = "v0=" + hmac.new(
            settings.slack_signing_secret.encode(), sig_base.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_slack_signature):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Slack sends form-encoded payloads for slash commands
    try:
        form = await request.form()
        text = str(form.get("text", "")).strip()
        command = str(form.get("command", ""))
        user_name = str(form.get("user_name", "unknown"))
    except Exception:
        payload = __import__("json").loads(body)
        text = payload.get("text", "")
        command = payload.get("command", "")
        user_name = payload.get("user_name", "unknown")

    if "/initiate_acp" in command or text.startswith("initiate_acp"):
        target_url = text.strip().split()[0] if text.strip() else ""
        if not target_url:
            return {"response_type": "ephemeral", "text": "Usage: /initiate_acp <url>"}

        task = run_acp_workflow_task.delay(target_url)
        memory_store.insert_transcript(
            run_id=task.id,
            agent_role="gateway-slack",
            role="user",
            content=f"ACP triggered from Slack by @{user_name} for {target_url}",
        )
        logger.info("Gateway (Slack): ACP triggered for %s → task %s", target_url, task.id)
        return {
            "response_type": "ephemeral",
            "text": f"✅ ACP initiated for `{target_url}` (Task `{task.id}`)",
        }

    return {"response_type": "ephemeral", "text": "Unknown command. Try `/initiate_acp <url>`"}


# ---------------------------------------------------------------------------
# Email (SendGrid / Postmark inbound parse)
# ---------------------------------------------------------------------------

@router.post("/email/inbound")
async def email_inbound(request: Request) -> Dict[str, Any]:
    """
    Accepts inbound email parse payloads from SendGrid or Postmark.
    Routes commands from whitelisted sender addresses.
    """
    settings = get_settings()
    payload = await request.json()

    # SendGrid uses 'from', Postmark uses 'From'
    sender = payload.get("from") or payload.get("From", "")
    body_text = payload.get("text") or payload.get("TextBody", "")

    whitelist = [s.strip() for s in settings.gateway_email_whitelist.split(",") if s.strip()]
    if whitelist and sender not in whitelist:
        logger.warning("Gateway (Email): rejected sender %s — not in whitelist.", sender)
        raise HTTPException(status_code=403, detail="Sender not authorised")

    for line in body_text.splitlines():
        line = line.strip()
        if line.lower().startswith("initiate_acp:"):
            target_url = line.split(":", 1)[1].strip()
            task = run_acp_workflow_task.delay(target_url)
            memory_store.insert_transcript(
                run_id=task.id,
                agent_role="gateway-email",
                role="user",
                content=f"ACP triggered via email from {sender} for {target_url}",
            )
            logger.info("Gateway (Email): ACP triggered for %s → task %s", target_url, task.id)
            return {"status": "success", "action": "acp_triggered", "task_id": task.id}

    return {"status": "ignored"}


# ---------------------------------------------------------------------------
# SMS (Twilio)
# ---------------------------------------------------------------------------

@router.post("/sms/inbound")
async def sms_inbound(
    request: Request,
    x_twilio_signature: str = Header(None),
) -> Dict[str, Any]:
    """
    Accepts Twilio SMS webhook payloads.
    Validates the X-Twilio-Signature HMAC and routes commands.
    """
    settings = get_settings()
    body = await request.body()

    if settings.twilio_auth_token:
        try:
            from urllib.parse import parse_qs, urlencode
            form_data = parse_qs(body.decode(), keep_blank_values=True)
            # Twilio signature = HMAC-SHA1 of URL + sorted params
            url = str(request.url)
            params = "".join(f"{k}{v[0]}" for k, v in sorted(form_data.items()))
            sig_base = (url + params).encode()
            expected = __import__("base64").b64encode(
                hmac.new(settings.twilio_auth_token.encode(), sig_base, __import__("hashlib").sha1).digest()
            ).decode()
            if not hmac.compare_digest(expected, x_twilio_signature or ""):
                raise HTTPException(status_code=401, detail="Invalid Twilio signature")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Twilio signature check error: %s", exc)

    try:
        from urllib.parse import parse_qs
        form = parse_qs(body.decode())
        sms_body = form.get("Body", [""])[0].strip()
        from_number = form.get("From", ["unknown"])[0]
    except Exception:
        return {"status": "ignored"}

    if sms_body.lower().startswith("acp "):
        target_url = sms_body[4:].strip()
        task = run_acp_workflow_task.delay(target_url)
        memory_store.insert_transcript(
            run_id=task.id,
            agent_role="gateway-sms",
            role="user",
            content=f"ACP triggered via SMS from {from_number} for {target_url}",
        )
        logger.info("Gateway (SMS): ACP triggered for %s → task %s", target_url, task.id)
        return {"status": "success", "action": "acp_triggered", "task_id": task.id}

    return {"status": "ignored"}

