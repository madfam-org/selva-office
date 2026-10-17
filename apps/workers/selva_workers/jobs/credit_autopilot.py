"""Credit-investment autopilot: MADFAM's tenant invests an expiring grant.

Off unless BOTH hold:

* env ``CREDIT_AUTOPILOT_ENABLED=true`` on the workers, and
* the provider grant (lane LG, contract C1) has ``autopilot: true``.

Every ``CREDIT_AUTOPILOT_INTERVAL_SECONDS`` (default 180) one worker replica
(Redis lock) reads grant status via
``madfam_inference.grants.get_grant_statuses()`` (contract C2; when that
module is absent the loop is a no-op), asks ``credit_autopilot_policy`` which
backlog items to start, and starts them for the platform org only
(``PLATFORM_ORG_ID``, default ``madfam``):

* ``generate`` items: a ``swarm_tasks`` row (label ``credit-autopilot``) is
  created, the router is called once with the provider pinned to the grant's
  provider and the chosen model tier, and the output is stored on the task
  (``payload.result``) with kanban status ``review``. Failures are recorded
  on the task (``failed`` + error) — never placeholder text.
* ``dispatch`` items: a ``swarm_tasks`` row + ``swarm_task_outbox`` row, the
  same durable path ``POST /swarms/dispatch`` uses; the worker outbox
  publisher puts it on ``selva:task-stream``.

Per-item status and spend attribution live on those task rows (task id ->
``compute_token_ledger.task_id``). The loop stops starting work at
exhaustion, expiry, the floor, or when the pace is ``ahead``; the grant guard
(LG) remains the hard stop for anything in flight.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .credit_autopilot_policy import (
    AutopilotConfig,
    BacklogItem,
    Decision,
    ItemState,
    Selection,
    choose_grant,
    parse_backlog,
    plan_dispatch,
)

logger = logging.getLogger(__name__)

LABEL = "credit-autopilot"
GENERATE_GRAPH_TYPE = "credit_generate"
LOCK_KEY = "selva:credit-autopilot:leader"
CONTEXT_FILE_MAX_BYTES = 120_000
CONTEXT_TOTAL_MAX_BYTES = 240_000
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_BACKLOG = _REPO_ROOT / "data" / "credit-investment" / "backlog.yaml"


def is_enabled() -> bool:
    return os.environ.get("CREDIT_AUTOPILOT_ENABLED", "").strip().lower() == "true"


def autopilot_org() -> str | None:
    """The only org the autopilot may act for: the platform org.

    ``CREDIT_AUTOPILOT_ORG_ID`` may restate it but can never point elsewhere.
    """
    platform = os.environ.get("PLATFORM_ORG_ID", "").strip() or "madfam"
    requested = os.environ.get("CREDIT_AUTOPILOT_ORG_ID", "").strip()
    if requested and requested != platform:
        logger.error(
            "credit autopilot: CREDIT_AUTOPILOT_ORG_ID differs from the platform org; refusing"
        )
        return None
    return platform


def load_config() -> AutopilotConfig:
    def num(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, "") or default)
        except ValueError:
            return default

    return AutopilotConfig(
        floor_usd=num("CREDIT_AUTOPILOT_FLOOR_USD", 2.0),
        max_concurrency=max(1, int(num("CREDIT_AUTOPILOT_MAX_CONCURRENCY", 6))),
        max_attempts=max(1, int(num("CREDIT_AUTOPILOT_MAX_ATTEMPTS", 2))),
    )


def load_backlog(path: Path | None = None) -> list[BacklogItem]:
    import yaml

    target = path or Path(os.environ.get("CREDIT_AUTOPILOT_BACKLOG_PATH") or _DEFAULT_BACKLOG)
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    return parse_backlog(data)


async def load_grant_statuses() -> list[Any] | None:
    """Return C2 grant statuses, or None when the grants module is absent."""
    # importlib keeps this typed (and free of type: ignore) whether or not
    # lane LG's module is present yet.
    try:
        grants = importlib.import_module("madfam_inference.grants")
    except ImportError:
        return None
    getter = getattr(grants, "get_grant_statuses", None)
    if getter is None:
        return None
    result = getter()
    if inspect.isawaitable(result):
        result = await result
    return list(result or [])


# -- DB ------------------------------------------------------------------------


def _db_url() -> str | None:
    from ..config import get_settings

    url = get_settings().database_url or os.environ.get("DATABASE_URL")
    return url or None


_SET_ORG_SQL = "SELECT set_config('app.current_org_id', :org, true)"

_STATES_SQL = """
SELECT id::text AS id, status,
       (payload::jsonb -> 'credit_autopilot' ->> 'item_id') AS item_id,
       (status IN ('pending', 'queued', 'running')
        AND updated_at < NOW() - INTERVAL '60 minutes') AS stale
  FROM swarm_tasks
 WHERE org_id = :org
   AND parent_task_id IS NULL
   AND labels::jsonb ? :label
"""

_INSERT_TASK_SQL = """
INSERT INTO swarm_tasks (
    id, title, description, graph_type, assigned_agent_ids, payload, status,
    kanban_status, priority, labels, depends_on, org_id, retry_count,
    created_at, updated_at, started_at
) VALUES (
    CAST(:id AS uuid), :title, :description, :graph_type, CAST('[]' AS json),
    CAST(:payload AS json), :status, :kanban_status, 'medium',
    CAST(:labels AS json), CAST('[]' AS json), :org, 0, NOW(), NOW(), :started_at
)
"""

_INSERT_OUTBOX_SQL = """
INSERT INTO swarm_task_outbox (
    id, task_id, org_id, stream_name, payload, status, retry_count, created_at, updated_at
) VALUES (
    CAST(:id AS uuid), CAST(:task_id AS uuid), :org, 'selva:task-stream',
    CAST(:payload AS json), 'pending', 0, NOW(), NOW()
)
"""

_FINISH_TASK_SQL = """
UPDATE swarm_tasks
   SET status = :status, kanban_status = :kanban_status,
       payload = CAST(:payload AS json), error_message = :error,
       completed_at = NOW(), updated_at = NOW()
 WHERE id = CAST(:id AS uuid) AND org_id = :org
"""


def summarise_states(rows: list[dict[str, Any]]) -> dict[str, ItemState]:
    """Collapse task rows to one state per item (attempts = rows per item)."""
    attempts: dict[str, int] = {}
    latest: dict[str, str] = {}
    priority = {"running": 3, "queued": 3, "pending": 3, "completed": 2}
    for row in rows:
        item_id = row.get("item_id")
        if not item_id:
            continue
        attempts[item_id] = attempts.get(item_id, 0) + 1
        # A row stuck in flight (dead pod) counts as a failed attempt so it
        # cannot hold a concurrency slot forever.
        status = "stale" if row.get("stale") else str(row.get("status") or "")
        current = latest.get(item_id)
        if current is None or priority.get(status, 0) > priority.get(current, 0):
            latest[item_id] = status
    return {i: ItemState(item_id=i, status=latest[i], attempts=attempts[i]) for i in latest}


async def _fetch_states(engine: Any, org: str) -> dict[str, ItemState]:
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text(_SET_ORG_SQL), {"org": org})
        result = await conn.execute(text(_STATES_SQL), {"org": org, "label": LABEL})
        rows = [dict(r) for r in result.mappings().all()]
    return summarise_states(rows)


def _task_payload(sel: Selection, grant_id: str, org: str, task_id: str) -> dict[str, Any]:
    return {
        "credit_autopilot": {
            "item_id": sel.item.id,
            "line": sel.item.line,
            "mode": sel.item.mode,
            "tier": sel.tier,
            "model": sel.model,
            "tier_enforced": sel.item.mode == "generate",
            "selection_reason": sel.reason,
            "grant_id": grant_id,
            "acceptance": list(sel.item.acceptance),
        },
        "_selva_envelope": {
            "schema": "selva.task-envelope/v1",
            "task_id": task_id,
            "org_id": org,
            "audience": "platform",
            "graph_type": sel.item.graph or GENERATE_GRAPH_TYPE,
            "idempotency_key": f"{LABEL}:{grant_id}:{sel.item.id}:{task_id}",
            "source": LABEL,
        },
    }


def _description(item: BacklogItem) -> str:
    acceptance = "\n".join(f"- {a}" for a in item.acceptance)
    return (
        f"[{LABEL}] {item.objective}\n\nDeliverable: {item.deliverable}\n\n"
        f"Acceptance:\n{acceptance}\n\nRead/draft only: no sends, posts, pushes, "
        "CRM, billing or production writes."
    )


async def _create_task(
    engine: Any, org: str, sel: Selection, grant_id: str, *, generate: bool
) -> tuple[str, dict[str, Any]]:
    from sqlalchemy import text

    task_id = str(uuid.uuid4())
    payload = _task_payload(sel, grant_id, org, task_id)
    graph_type = GENERATE_GRAPH_TYPE if generate else str(sel.item.graph)
    async with engine.begin() as conn:
        await conn.execute(text(_SET_ORG_SQL), {"org": org})
        await conn.execute(
            text(_INSERT_TASK_SQL),
            {
                "id": task_id,
                "title": f"[{LABEL}] {sel.item.id}"[:200],
                "description": _description(sel.item),
                "graph_type": graph_type,
                "payload": json.dumps(payload),
                "status": "running" if generate else "pending",
                "kanban_status": "in_progress" if generate else "todo",
                "labels": json.dumps(
                    [LABEL, f"line:{sel.item.line}", sel.item.id, f"item:{sel.item.id}"]
                ),
                "org": org,
                "started_at": datetime.now(UTC) if generate else None,
            },
        )
        if not generate:
            message = {
                **payload["_selva_envelope"],
                "description": _description(sel.item),
                "assigned_agent_ids": [],
                "required_skills": [],
                "payload": payload,
            }
            await conn.execute(
                text(_INSERT_OUTBOX_SQL),
                {
                    "id": str(uuid.uuid4()),
                    "task_id": task_id,
                    "org": org,
                    "payload": json.dumps(message),
                },
            )
    return task_id, payload


async def _finish_task(
    engine: Any,
    org: str,
    task_id: str,
    payload: dict[str, Any],
    *,
    ok: bool,
    error: str | None = None,
) -> None:
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text(_SET_ORG_SQL), {"org": org})
        await conn.execute(
            text(_FINISH_TASK_SQL),
            {
                "id": task_id,
                "org": org,
                "status": "completed" if ok else "failed",
                "kanban_status": "review" if ok else "blocked",
                "payload": json.dumps(payload),
                "error": (error or "")[:2000] or None,
            },
        )


# -- generate mode -------------------------------------------------------------


async def fetch_context(
    context: tuple[tuple[str, str], ...],
) -> tuple[list[tuple[str, str]], list[str]]:
    """Fetch public madfam-org files (read-only). Returns (files, missing)."""
    import httpx

    files: list[tuple[str, str]] = []
    missing: list[str] = []
    total = 0
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        for repo, path in context:
            label = f"{repo}/{path}"
            if "/" in repo or ".." in path or path.startswith("/"):
                missing.append(f"{label} (rejected path)")
                continue
            url = f"https://raw.githubusercontent.com/madfam-org/{repo}/HEAD/{path}"
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                missing.append(f"{label} ({exc.__class__.__name__})")
                continue
            if resp.status_code != 200:
                missing.append(f"{label} (HTTP {resp.status_code})")
                continue
            body = resp.text[:CONTEXT_FILE_MAX_BYTES]
            if total + len(body) > CONTEXT_TOTAL_MAX_BYTES:
                missing.append(f"{label} (context budget)")
                continue
            total += len(body)
            files.append((label, body))
    return files, missing


def _load_line_context(line_id: str) -> str:
    try:
        import yaml

        roster = yaml.safe_load(
            (_REPO_ROOT / "data" / "factory-lines" / "madfam-factory-lines.yaml").read_text(
                encoding="utf-8"
            )
        )
        for line in roster.get("lines", []):
            if line.get("id") == line_id:
                return (
                    f"Factory line: {line.get('name')}. Products: "
                    f"{', '.join(line.get('products', []))}. Tools: "
                    f"{', '.join(line.get('tools', []))}."
                )
    except Exception:
        logger.debug("factory-lines roster unavailable", exc_info=True)
    return ""


# -- tick ----------------------------------------------------------------------


async def _acquire_lock(ttl_seconds: int) -> bool:
    from selva_redis_pool import get_redis_pool

    try:
        acquired = await get_redis_pool().execute_with_retry(
            "set", LOCK_KEY, str(os.getpid()), nx=True, ex=ttl_seconds, max_retries=1
        )
    except Exception:
        logger.warning("credit autopilot: Redis lock unavailable; skipping tick", exc_info=True)
        return False
    return bool(acquired)


async def tick(inflight: set[asyncio.Task[None]]) -> Decision | None:
    """One autopilot pass. Returns the decision, or None when idle."""
    if not is_enabled():
        return None
    org = autopilot_org()
    if org is None:
        return None
    statuses = await load_grant_statuses()
    if statuses is None:
        logger.info("credit autopilot: grants module not available; idle")
        return None
    grant = choose_grant(statuses)
    if grant is None:
        return None
    db_url = _db_url()
    if not db_url:
        logger.error("credit autopilot: DATABASE_URL unset; cannot record work")
        return None

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, pool_pre_ping=True)
    try:
        states = await _fetch_states(engine, org)
        items = load_backlog()
        decision = plan_dispatch(grant, items, states, load_config())
        logger.info(
            "credit autopilot: grant=%s pace=%s decision=%s selections=%s skipped=%s",
            grant.id,
            grant.pace_status,
            decision.reason,
            [(s.item.id, s.tier) for s in decision.selections],
            decision.skipped,
        )
        for sel in decision.selections:
            if sel.item.mode == "dispatch":
                await _create_task(engine, org, sel, grant.id, generate=False)
                continue
            # Generate items own their engine so the tick's engine can close.
            task = asyncio.create_task(_run_generate_in_own_engine(db_url, org, sel, grant))
            inflight.add(task)
            task.add_done_callback(inflight.discard)
        return decision
    finally:
        await engine.dispose()


async def _run_generate_in_own_engine(db_url: str, org: str, sel: Selection, grant: Any) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url, pool_pre_ping=True)
    try:
        from .credit_autopilot_exec import run_item

        await run_item(engine, org, sel, grant)
    except Exception:
        logger.exception("credit autopilot generate item %s crashed", sel.item.id)
    finally:
        await engine.dispose()


async def periodic_loop(shutdown: asyncio.Event) -> None:
    """Run the autopilot until shutdown (idle unless enabled)."""
    if not is_enabled():
        logger.info("Credit autopilot disabled (CREDIT_AUTOPILOT_ENABLED != true)")
        return
    interval = max(30, int(os.environ.get("CREDIT_AUTOPILOT_INTERVAL_SECONDS", "180") or 180))
    inflight: set[asyncio.Task[None]] = set()
    while not shutdown.is_set():
        try:
            if await _acquire_lock(ttl_seconds=interval - 5):
                await tick(inflight)
        except Exception:
            logger.exception("Credit autopilot tick failed")
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=interval)
        except TimeoutError:
            continue
    if inflight:
        await asyncio.gather(*inflight, return_exceptions=True)
