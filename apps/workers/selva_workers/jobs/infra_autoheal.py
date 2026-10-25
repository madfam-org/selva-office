"""Worker job for the infra self-healing agent, v1 diagnose-and-propose (RFC 0047).

Off unless ``INFRA_AUTOHEAL_ENABLED=true``; with it on but the caps or the
alert allowlist missing, the job logs ERROR and stays idle (fail closed).

Each tick (one replica, Redis lock) pops ONE queued incident and:

1. opens a durable record — a swarm task in the platform org, labelled
   ``infra-autoheal`` and ``incident:<key>`` (the task board's Review column);
2. runs ``selva_autoheal.agent.DiagnosisAgent``: Enclii reads first, then a
   bounded model loop on the funded credentials, preferred in
   ``INFRA_AUTOHEAL_PROVIDERS`` order (``anthropic-ops`` then ``anthropic``),
   each only under its own grant and under the per-incident and daily caps;
3. posts the report to the incident chat through angelia Courier;
4. closes the record with the report, the spend, the tool audit and the
   delivery result.

HARD RULE: v1 never writes to production. The toolbox can only read and
dry-run; applying a plan is a human action in Enclii with the plan hash.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from selva_autoheal import courier
from selva_autoheal.agent import DiagnosisAgent, DiagnosisReport, LLMReply, LLMUnavailable
from selva_autoheal.alerts import IncidentSignal
from selva_autoheal.config import AutohealConfig, ConfigError
from selva_autoheal.report import render
from selva_autoheal.store import PREFIX, IncidentStore
from selva_autoheal.tools import Toolbox, httpx_transport

logger = logging.getLogger(__name__)

LABEL = "infra-autoheal"
GRAPH_TYPE = "infra-autoheal"
LOCK_KEY = PREFIX + "lock"
DEFAULT_POLL_SECONDS = 15


# -- model client ----------------------------------------------------------------


class RouterLLM:
    """The model client: Selva's router, server-side allowlist, ledger metering."""

    def __init__(self, cfg: AutohealConfig, task_id: str | None) -> None:
        self.cfg = cfg
        self.task_id = task_id

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        providers: tuple[str, ...],
        model: str,
        max_tokens: int,
        incident_key: str,
    ) -> LLMReply:
        from madfam_inference.grants import ProviderGrantUnavailableError
        from madfam_inference.types import InferenceRequest, RoutingPolicy, Sensitivity

        from ..inference import get_model_router
        from ..metering import meter_inference_call

        request = InferenceRequest(
            messages=messages,
            system_prompt=system,
            policy=RoutingPolicy(
                sensitivity=Sensitivity.INTERNAL,
                max_tokens=max_tokens,
                temperature=0.2,
                org_id=self.cfg.org_id,
                # Server-set narrowing: only these credentials, in this order,
                # each still behind its own grant (the guard is the hard stop).
                provider_allowlist=list(providers),
                provider_models={p: model for p in providers},
            ),
        )
        try:
            response = await get_model_router().complete(request)
        except ProviderGrantUnavailableError as exc:
            raise LLMUnavailable(str(exc), no_budget=True) from exc
        except RuntimeError as exc:
            no_provider = "No available provider" in str(exc)
            raise LLMUnavailable(str(exc)[:300], no_budget=no_provider) from exc
        except Exception as exc:
            raise LLMUnavailable(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
        usage = dict(response.usage or {})
        if usage:
            await meter_inference_call(
                usage=usage,
                provider=response.provider,
                model=response.model,
                task_id=self.task_id,
                org_id=self.cfg.org_id,
                task_type=None,
            )
        return LLMReply(
            content=response.content or "",
            provider=response.provider,
            model=response.model,
            usage={k: int(v or 0) for k, v in usage.items() if isinstance(v, int | float)},
        )


# -- budget ----------------------------------------------------------------------


def funded_from_statuses(providers: tuple[str, ...], statuses: list[Any]) -> tuple[str, ...]:
    """Providers (in order) with a live grant that still has budget.

    A provider with no grant, an expired or exhausted grant, or an unreadable
    meter is left out, so the model client never even offers it.
    """
    out: list[str] = []
    for name in providers:
        for st in statuses:
            if getattr(st, "provider", None) != name:
                continue
            remaining = getattr(st, "remaining_usd", None)
            if (
                getattr(st, "active", False)
                and getattr(st, "meter_ok", False)
                and remaining is not None
                and float(remaining) > 0
                and getattr(st, "pace_status", "") not in ("exhausted", "expired", "unknown")
            ):
                out.append(name)
                break
    return tuple(out)


async def funded_providers(providers: tuple[str, ...]) -> tuple[str, ...]:
    try:
        from madfam_inference.grants import get_grant_statuses

        statuses = await get_grant_statuses()
    except Exception:
        logger.exception("infra autoheal: cannot read grant statuses; treating as no budget")
        return ()
    return funded_from_statuses(providers, list(statuses))


def _price(provider: str, model: str, inp: int, out: int) -> float:
    from madfam_budget_gate.cost_model import estimate_cost

    return float(estimate_cost(provider, model, inp, out))


# -- durable record ----------------------------------------------------------------


async def _open_record(cfg: AutohealConfig, signal: IncidentSignal) -> tuple[Any, str] | None:
    """Insert the incident's swarm task (status running). None without a DB."""
    from .credit_autopilot import _INSERT_TASK_SQL, _SET_ORG_SQL, _db_url

    url = _db_url()
    if not url:
        logger.error("infra autoheal: no DATABASE_URL; incident %s kept in Redis only",
                     signal.key)
        return None
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url, pool_pre_ping=True)
    task_id = str(uuid.uuid4())
    payload = {"infra_autoheal": {"incident": signal.to_dict(), "state": "diagnosing"}}
    async with engine.begin() as conn:
        await conn.execute(text(_SET_ORG_SQL), {"org": cfg.org_id})
        await conn.execute(
            text(_INSERT_TASK_SQL),
            {
                "id": task_id,
                "title": f"[{LABEL}] {signal.alertname} {signal.namespace}"[:200],
                "description": (
                    f"[{LABEL}] Diagnosis of incident {signal.key}. Read-only: v1 never "
                    "writes to production; a remedy is a plan a human applies."
                ),
                "graph_type": GRAPH_TYPE,
                "payload": json.dumps(payload),
                "status": "running",
                "kanban_status": "in_progress",
                "labels": json.dumps([LABEL, f"incident:{signal.key}"]),
                "org": cfg.org_id,
                "started_at": datetime.now(UTC),
            },
        )
    return engine, task_id


async def _close_record(
    cfg: AutohealConfig, handle: tuple[Any, str] | None, record: dict[str, Any], ok: bool
) -> None:
    if handle is None:
        return
    from sqlalchemy import text

    from .credit_autopilot import _FINISH_TASK_SQL, _SET_ORG_SQL

    engine, task_id = handle
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_SET_ORG_SQL), {"org": cfg.org_id})
            await conn.execute(
                text(_FINISH_TASK_SQL),
                {
                    "id": task_id,
                    "org": cfg.org_id,
                    "status": "completed" if ok else "failed",
                    "kanban_status": "review" if ok else "blocked",
                    "payload": json.dumps({"infra_autoheal": record}, default=str),
                    "error": None if ok else str(record.get("error") or "")[:2000] or None,
                },
            )
    finally:
        await engine.dispose()


# -- one incident ------------------------------------------------------------------


def _toolbox(cfg: AutohealConfig) -> Toolbox:
    token = os.environ.get(cfg.enclii_token_env, "")
    if not (cfg.enclii_api_url and token):
        logger.error("infra autoheal: ENCLII API URL or %s unset; reads will fail visibly",
                     cfg.enclii_token_env)
        return Toolbox(None)
    return Toolbox(httpx_transport(cfg.enclii_api_url, token))


async def run_incident(
    cfg: AutohealConfig,
    store: IncidentStore,
    signal: IncidentSignal,
    *,
    agent: DiagnosisAgent | None = None,
    post: courier.PostFn | None = None,
    record_db: bool = True,
) -> dict[str, Any]:
    """Diagnose one incident, post the report, keep the record. Returns the record."""
    now = datetime.now(tz=UTC)
    handle = None
    if record_db:
        try:
            handle = await _open_record(cfg, signal)
        except Exception:
            logger.exception("infra autoheal: cannot open the task record for %s", signal.key)
    task_id = handle[1] if handle else None
    record: dict[str, Any] = {"incident": signal.to_dict(), "task_id": task_id}
    ok = False
    try:
        runner = agent or DiagnosisAgent(
            cfg=cfg,
            toolbox=_toolbox(cfg),
            llm=RouterLLM(cfg, task_id),
            price=_price,
            funded=funded_providers,
            killed=store.killed,
        )
        report: DiagnosisReport = await runner.run(signal, await store.spend_today(now))
        await store.add_spend(report.spent_usd, now)
        text = render(report)
        # A re-diagnosis of the same incident threads under its first report
        # (only with INFRA_AUTOHEAL_COURIER_THREADING; see selva_autoheal.courier).
        first_delivery = (await store.record(signal.key) or {}).get("first_delivery_id")
        delivery = await courier.send(
            cfg,
            text=text,
            idempotency_key=f"selva-autoheal:{signal.key}:{task_id or now.isoformat()}:diagnosis",
            urgent=signal.severity == "critical",
            reply_to=first_delivery,
            post=post,
        )
        if delivery.sent and delivery.delivery_id and not first_delivery:
            record["first_delivery_id"] = delivery.delivery_id
        if not delivery.sent:
            logger.error("infra autoheal: report for %s not delivered (%s %s)", signal.key,
                         delivery.status, delivery.detail)
        record.update(
            {"state": "reported", "report": report.to_dict(), "text": text,
             "delivery": delivery.__dict__}
        )
        ok = True
    except ConfigError as exc:
        record.update({"state": "refused", "error": str(exc)})
        logger.error("infra autoheal: not running (%s)", exc)
    except Exception as exc:
        record.update({"state": "failed", "error": f"{type(exc).__name__}: {str(exc)[:500]}"})
        logger.exception("infra autoheal: incident %s failed", signal.key)
    finally:
        previous = await store.record(signal.key) or {}
        await store.put_record(signal.key, {**previous, **record, "finished_at": now.isoformat()})
        try:
            await _close_record(cfg, handle, record, ok)
        except Exception:
            logger.exception("infra autoheal: cannot close the task record for %s", signal.key)
    return record


# -- loop ----------------------------------------------------------------------------


async def _acquire_lock(redis: Any, ttl_seconds: int) -> bool:
    try:
        return bool(await redis.set(LOCK_KEY, str(os.getpid()), nx=True, ex=ttl_seconds))
    except Exception:
        logger.warning("infra autoheal: Redis lock unavailable; skipping tick", exc_info=True)
        return False


async def tick(cfg: AutohealConfig, redis: Any) -> dict[str, Any] | None:
    store = IncidentStore(redis, cfg)
    if not await _acquire_lock(redis, cfg.max_seconds + 120):
        return None
    try:
        signal = await store.pop()
        if signal is None:
            return None
        return await run_incident(cfg, store, signal)
    finally:
        await redis.delete(LOCK_KEY)


async def periodic_loop(shutdown: asyncio.Event) -> None:
    """Run until shutdown. Idle unless enabled and fully configured."""
    cfg = AutohealConfig.from_env()
    if not cfg.enabled:
        logger.info("Infra autoheal disabled (INFRA_AUTOHEAL_ENABLED != true)")
        return
    try:
        cfg.validate_for_run()
    except ConfigError as exc:
        logger.error("Infra autoheal enabled but NOT running: %s", exc)
        return
    from selva_redis_pool import get_redis_pool

    interval = max(5, int(os.environ.get("INFRA_AUTOHEAL_POLL_SECONDS", DEFAULT_POLL_SECONDS)))
    logger.info("Infra autoheal running (diagnose-and-propose only; providers %s)",
                ",".join(cfg.providers))
    while not shutdown.is_set():
        try:
            await tick(cfg, await get_redis_pool().client())
        except Exception:
            logger.exception("Infra autoheal tick failed")
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=interval)
        except TimeoutError:
            continue
