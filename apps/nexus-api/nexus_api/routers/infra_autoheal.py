"""Alertmanager receiver for the infra self-healing agent (RFC 0047).

``POST /api/v1/infra/autoheal/alertmanager`` — Alertmanager's
``webhook_config`` with ``http_config.authorization`` (Bearer).

- Off by default: ``INFRA_AUTOHEAL_ENABLED`` unset ⇒ 503 ``autoheal_disabled``.
- ``INFRA_AUTOHEAL_WEBHOOK_SECRET`` unset ⇒ 503 (an unset secret is a
  misconfiguration, never "accept anything"); wrong token ⇒ 401.
- The route only records and queues (Redis, ``selva_autoheal.store``). It never
  calls a model, Enclii or Courier; the worker job does the diagnosis.
- Not in the OpenAPI schema: it is an in-cluster webhook, like the gateway
  and Dhanam webhooks, not a client API.
"""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from selva_autoheal.config import AutohealConfig
from selva_autoheal.intake import InvalidPayload, handle
from selva_autoheal.store import IncidentStore

from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["infra-autoheal"])

MAX_BODY_BYTES = 1_000_000


def get_autoheal_config() -> AutohealConfig:
    return AutohealConfig.from_env()


async def get_autoheal_store(cfg: AutohealConfig) -> IncidentStore:
    """The Redis-backed incident store (tests replace this module function)."""
    from selva_redis_pool import get_redis_pool

    return IncidentStore(await get_redis_pool().client(), cfg)


def _check_bearer(authorization: str | None) -> None:
    secret = get_settings().infra_autoheal_webhook_secret
    if not secret:
        logger.error("infra autoheal webhook received but INFRA_AUTOHEAL_WEBHOOK_SECRET is unset")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "webhook endpoint not configured")
    presented = (authorization or "").removeprefix("Bearer ").removeprefix("bearer ")
    if not presented or not hmac.compare_digest(presented.encode(), secret.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook credential")


@router.post(
    "/infra/autoheal/alertmanager",
    include_in_schema=False,
    status_code=status.HTTP_202_ACCEPTED,
)
async def alertmanager_webhook(
    request: Request,
    authorization: str | None = Header(None),
    cfg: AutohealConfig = Depends(get_autoheal_config),
) -> dict[str, Any]:
    if not cfg.enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "autoheal_disabled")
    _check_bearer(authorization)
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload too large")
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "body is not JSON") from exc
    store = await get_autoheal_store(cfg)
    try:
        result = await handle(body, store, cfg, datetime.now(tz=UTC))
    except InvalidPayload as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    logger.info(
        "infra autoheal intake: incident=%s decision=%s reason=%s",
        result.incident_key,
        result.decision,
        result.reason,
    )
    return {"incident": result.to_dict()}
