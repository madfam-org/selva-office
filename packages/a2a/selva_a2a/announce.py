"""Optional task announcer to a configurable observability intake.

When a newly created A2A task should be surfaced to an external observability
appservice, this module POSTs a compact announcement to a configurable intake
URL. A2A itself defines no server-push of *new* tasks, so the observer exposes
its own intake endpoint that the agent side POSTs to when it creates a task.

The counterpart keeps platform names out of code, so this module does too: the
intake is configured purely via generic env vars — ``A2A_OBSERVER_INTAKE_URL``
(and optional bearer ``A2A_OBSERVER_INTAKE_TOKEN``). No product/platform name
appears here.

Design constraints (from the integration contract):
- OFF by default: when ``A2A_OBSERVER_INTAKE_URL`` is absent/blank, nothing is
  sent and :func:`announce_task` returns immediately.
- Fire-and-forget with bounded retry (3 attempts, jittered backoff).
- NEVER blocks or fails the run: every error is logged and swallowed. A caller
  can ``await announce_task(...)`` inline safe in the knowledge it will not
  raise. (For hard fire-and-forget, schedule it on the loop — see
  :func:`schedule_announcement`.)

This mirrors the resilience posture of
``apps/nexus-api/nexus_api/task_notification_notifier.py`` (best-effort Redis +
optional signed webhook; failures logged and swallowed).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Generic env keys — no platform name. GROUNDED: the observer side reads a
# matching generic intake URL + optional bearer token.
ENV_INTAKE_URL = "A2A_OBSERVER_INTAKE_URL"
ENV_INTAKE_TOKEN = "A2A_OBSERVER_INTAKE_TOKEN"  # noqa: S105 - env var *name*, not a secret

_DEFAULT_ATTEMPTS = 3
_DEFAULT_TIMEOUT_SECONDS = 3.0
_DEFAULT_BASE_BACKOFF_SECONDS = 0.25


def _configured_intake_url() -> str | None:
    """Return the validated intake URL, or ``None`` when the announcer is off."""
    raw = os.environ.get(ENV_INTAKE_URL, "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("Ignoring invalid %s: %r", ENV_INTAKE_URL, raw)
        return None
    return raw


def is_announcer_enabled() -> bool:
    """True when a valid intake URL is configured (announcer is on)."""
    return _configured_intake_url() is not None


def build_announcement(
    *,
    task_id: str,
    state: str,
    agent_card_url: str,
    update: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Build the announcement body for a newly created task.

    Shape (per contract): ``{id, status, agent card URL}``. ``status`` is the
    A2A v1 SCREAMING_SNAKE task-state string; ``agentCardUrl`` points the
    observer at this agent's v1.0.1 card so it can start observing. ``update``
    and ``tenant`` are included only when present.
    """
    body: dict[str, Any] = {
        "id": task_id,
        "status": {"state": state},
        "agentCardUrl": agent_card_url,
    }
    if update is not None:
        body["status"]["update"] = update
    if tenant is not None:
        body["tenant"] = tenant
    return body


async def announce_task(
    *,
    task_id: str,
    state: str,
    agent_card_url: str,
    update: str | None = None,
    tenant: str | None = None,
    attempts: int = _DEFAULT_ATTEMPTS,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    base_backoff_seconds: float = _DEFAULT_BASE_BACKOFF_SECONDS,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """POST a newly-created-task announcement to the configured intake.

    Returns ``True`` if the intake accepted the announcement (HTTP < 400),
    ``False`` otherwise (including when the announcer is off). NEVER raises —
    all transport/HTTP errors are logged and swallowed so the run is never
    blocked or failed by announcer trouble.

    Retries up to ``attempts`` times with jittered exponential-ish backoff on
    transport errors and 5xx responses. A 4xx is treated as a permanent reject
    (no retry) since retrying a malformed/unauthorized announcement won't help.

    Parameters
    ----------
    client:
        Optional injected :class:`httpx.AsyncClient` (used by tests against a
        local server). When ``None`` a short-lived client is created per call.
    """
    intake_url = _configured_intake_url()
    if intake_url is None:
        # Announcer is off — the default. Silent no-op.
        return False

    body = build_announcement(
        task_id=task_id,
        state=state,
        agent_card_url=agent_card_url,
        update=update,
        tenant=tenant,
    )
    headers = {"Content-Type": "application/json"}
    token = os.environ.get(ENV_INTAKE_TOKEN, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout_seconds)
    try:
        for attempt in range(1, max(1, attempts) + 1):
            try:
                resp = await http.post(intake_url, json=body, headers=headers)
            except Exception:
                logger.warning(
                    "Task announcement to intake failed (attempt %d/%d)",
                    attempt,
                    attempts,
                    exc_info=True,
                )
            else:
                if resp.status_code < 400:
                    return True
                if 400 <= resp.status_code < 500:
                    # Permanent client error — do not retry.
                    logger.warning(
                        "Task announcement rejected by intake with status %s; not retrying",
                        resp.status_code,
                    )
                    return False
                logger.warning(
                    "Task announcement got status %s from intake (attempt %d/%d)",
                    resp.status_code,
                    attempt,
                    attempts,
                )
            # Backoff before the next attempt (skip after the last one).
            if attempt < attempts:
                delay = base_backoff_seconds * (2 ** (attempt - 1))
                jittered = delay * (0.5 + random.random())
                await asyncio.sleep(jittered)
        return False
    finally:
        if owns_client:
            await http.aclose()


def schedule_announcement(
    *,
    task_id: str,
    state: str,
    agent_card_url: str,
    update: str | None = None,
    tenant: str | None = None,
) -> asyncio.Task[bool] | None:
    """Fire-and-forget helper: schedule :func:`announce_task` on the loop.

    Returns the created :class:`asyncio.Task`, or ``None`` when the announcer is
    off (so callers can cheaply skip). The task is detached; its result/errors
    are handled inside :func:`announce_task` (which never raises). A done
    callback consumes any unexpected exception so it never surfaces as an
    "exception was never retrieved" warning.
    """
    if not is_announcer_enabled():
        return None

    coro = announce_task(
        task_id=task_id,
        state=state,
        agent_card_url=agent_card_url,
        update=update,
        tenant=tenant,
    )
    task = asyncio.ensure_future(coro)

    def _consume(t: asyncio.Task[bool]) -> None:
        # announce_task never raises, but guard defensively so a detached task
        # can never emit an unretrieved-exception warning.
        with __import__("contextlib").suppress(Exception):
            t.result()

    task.add_done_callback(_consume)
    return task
