"""Delivery through angelia Courier (``POST /v1/courier/send``, ADR-0010).

Selva is a Courier *producer*: it holds a producer key and sends envelopes;
Courier owns the Telegram bot. The envelope is the existing contract:
``tenant, channel, recipient{kind,ref}, body{kind:raw,text}, idempotency_key,
priority, consent{class}``. Unknown fields are refused by Courier (``.strict()``),
so ``reply_to`` (threading under the incident's first message) is sent ONLY
when ``INFRA_AUTOHEAL_COURIER_THREADING=true``, after angelia accepts it.

Without a configured URL, key, tenant or recipient nothing is sent and the
caller records ``not_configured`` — never a silent drop.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .config import AutohealConfig

#: ``post(url, headers, json) -> (status, body)``
PostFn = Callable[[str, dict[str, str], dict[str, Any]], Awaitable[tuple[int, Any]]]


@dataclass(frozen=True)
class Delivery:
    sent: bool
    status: str  # sent | replayed | not_configured | rejected | error
    delivery_id: str | None = None
    detail: str = ""


def build_envelope(
    cfg: AutohealConfig,
    *,
    text: str,
    idempotency_key: str,
    urgent: bool,
    reply_to: str | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "tenant": cfg.courier_tenant,
        "channel": "telegram",
        "recipient": {"kind": "telegram_chat", "ref": cfg.courier_recipient},
        "body": {"kind": "raw", "text": text[:4096]},
        "idempotency_key": idempotency_key[:200],
        "priority": "urgent" if urgent else "normal",
        "consent": {"class": "operational", "basis": "platform on-call (infra autoheal)"},
    }
    if cfg.courier_threading and reply_to:
        envelope["reply_to"] = {"delivery_id": reply_to}
    return envelope


async def _httpx_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        resp = await client.post(url, json=body, headers=headers)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, resp.text[:500]


async def send(
    cfg: AutohealConfig,
    *,
    text: str,
    idempotency_key: str,
    urgent: bool = True,
    reply_to: str | None = None,
    post: PostFn | None = None,
    env: dict[str, str] | None = None,
) -> Delivery:
    key = (env if env is not None else os.environ).get(cfg.courier_api_key_env, "")
    if not (cfg.courier_url and key and cfg.courier_tenant and cfg.courier_recipient):
        return Delivery(False, "not_configured", detail="courier url/key/tenant/recipient unset")
    envelope = build_envelope(
        cfg, text=text, idempotency_key=idempotency_key, urgent=urgent, reply_to=reply_to
    )
    headers = {"X-Internal-API-Key": key}  # Courier producer-key header
    try:
        status, body = await (post or _httpx_post)(
            cfg.courier_url.rstrip("/") + "/v1/courier/send", headers, envelope
        )
    except Exception as exc:
        return Delivery(False, "error", detail=type(exc).__name__)
    delivery = body.get("delivery") if isinstance(body, dict) else None
    delivery_id = str(delivery.get("id")) if isinstance(delivery, dict) and delivery.get("id") else None
    if status in (200, 201):
        return Delivery(True, "replayed" if status == 200 else "sent", delivery_id)
    error = body.get("error") if isinstance(body, dict) else None
    return Delivery(False, "rejected", detail=f"HTTP {status} {error or ''}".strip())
