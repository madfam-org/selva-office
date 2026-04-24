"""Health and readiness probe endpoints."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from selva_redis_pool import get_redis_pool

from ..config import get_settings
from ..database import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_settings = get_settings()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe -- always returns 200 if the process is running."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "service": "nexus-api",
    }


@router.get("/ready")
async def ready(response: Response) -> dict[str, object]:
    """Readiness probe -- validates database and Redis connectivity.

    Returns 200 when all dependencies are reachable, 503 otherwise.
    """
    checks: dict[str, str] = {}

    # -- Database check -------------------------------------------------------
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Database readiness check failed: %s", exc)
        checks["database"] = "unavailable"

    # -- Redis check ----------------------------------------------------------
    try:
        pool = get_redis_pool(url=_settings.redis_url)
        if await pool.ping():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable"
    except Exception as exc:
        logger.error("Redis readiness check failed: %s", exc)
        checks["redis"] = "unavailable"

    # -- Aggregate result -----------------------------------------------------
    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }


@router.get("/detail")
async def health_detail(response: Response) -> dict[str, object]:
    """Detailed health check including Colyseus connectivity and pool metrics."""
    checks: dict[str, str] = {}

    # -- Database check -------------------------------------------------------
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        checks["database"] = "unavailable"

    # -- Redis check ----------------------------------------------------------
    pool = get_redis_pool(url=_settings.redis_url)
    try:
        if await pool.ping():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable"
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        checks["redis"] = "unavailable"

    # -- Colyseus check -------------------------------------------------------
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            _colyseus_url = os.environ.get("COLYSEUS_URL", "http://localhost:4303")
            resp = await client.get(f"{_colyseus_url}/health")
            checks["colyseus"] = "ok" if resp.status_code == 200 else "degraded"
    except Exception:
        logger.debug("Colyseus health check failed", exc_info=True)
        checks["colyseus"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if all_ok else "degraded",
        "version": "0.1.0",
        "service": "nexus-api",
        "checks": checks,
        "redis_pool": pool.metrics(),
    }


@router.get("/pool-stats")
async def pool_stats() -> dict[str, object]:
    """Return database connection pool statistics."""
    from sqlalchemy.pool import QueuePool

    from ..database import get_engine

    eng = get_engine()
    pool = eng.pool
    if not isinstance(pool, QueuePool):
        return {"error": "pool is not a QueuePool", "status": pool.status()}
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.status(),
    }


@router.get("/queue-stats")
async def queue_stats() -> dict[str, object]:
    """Return Redis task stream and queue statistics."""
    pool = get_redis_pool(url=_settings.redis_url)
    stats: dict[str, object] = {}

    try:
        client = await pool.client()

        # Stream length
        try:
            stats["stream_length"] = await client.xlen("autoswarm:task-stream")
        except Exception:
            logger.debug("Failed to fetch stream length", exc_info=True)
            stats["stream_length"] = 0

        # DLQ depth
        try:
            stats["dlq_depth"] = await client.xlen("autoswarm:task-dlq")
        except Exception:
            logger.debug("Failed to fetch DLQ depth", exc_info=True)
            stats["dlq_depth"] = 0

        # Consumer group info
        try:
            groups = await client.xinfo_groups("autoswarm:task-stream")
            stats["consumer_groups"] = [
                {
                    "name": g.get("name", ""),
                    "consumers": g.get("consumers", 0),
                    "pending": g.get("pending", 0),
                    "last_delivered_id": g.get("last-delivered-id", ""),
                }
                for g in groups
            ]
        except Exception:
            logger.debug("Failed to fetch consumer group info", exc_info=True)
            stats["consumer_groups"] = []

    except Exception as exc:
        logger.warning("Failed to fetch queue stats: %s", exc)
        stats["error"] = str(exc)

    stats["redis_pool"] = pool.metrics()
    return stats


@router.get("/dlq-stats")
async def dlq_stats() -> dict[str, object]:
    """Return dead-letter queue statistics and recent entries."""
    pool = get_redis_pool(url=_settings.redis_url)
    result: dict[str, object] = {}

    try:
        client = await pool.client()

        try:
            result["depth"] = await client.xlen("autoswarm:task-dlq")
        except Exception:
            logger.debug("Failed to fetch DLQ depth", exc_info=True)
            result["depth"] = 0

        # Return the 10 most recent DLQ entries.
        try:
            entries = await client.xrevrange("autoswarm:task-dlq", count=10)
            result["recent"] = [{"id": eid, "data": data} for eid, data in entries]
        except Exception:
            logger.debug("Failed to fetch recent DLQ entries", exc_info=True)
            result["recent"] = []

    except Exception as exc:
        logger.warning("Failed to fetch DLQ stats: %s", exc)
        result["error"] = str(exc)

    return result
