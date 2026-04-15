"""FastAPI application factory for the AutoSwarm Nexus API."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from autoswarm_observability import init_sentry, init_tracing
from autoswarm_redis_pool import get_redis_pool

from .analytics import init_posthog
from .analytics import shutdown as shutdown_posthog
from .config import get_settings
from .database import engine
from .logging_config import configure_logging
from .middleware.csrf import CSRFMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIdMiddleware
from .middleware.security import SecurityHeadersMiddleware, TenantRLSMiddleware
from .routers import (
    admin,
    agents,
    approvals,
    artifacts,
    billing,
    billing_internal,
    calendar,
    chat,
    checkpoints,
    command_approvals,
    departments,
    events,
    gateway,
    health,
    intelligence,
    maps,
    marketplace,
    metrics,
    schedules,
    skills,
    skills_hub,
    swarms,
    trajectories,
    voice,
    workflows,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager.

    Initializes the async database engine, Redis pool, and verifies
    connectivity on startup, then disposes resources on shutdown.
    """
    settings = get_settings()

    # -- Startup --------------------------------------------------------------
    init_posthog()
    logger.info("Nexus API starting on port %d", settings.port)

    # Verify database engine connectivity.
    async with engine.begin() as conn:
        await conn.run_sync(lambda _conn: None)  # connection check
    logger.info("Database engine initialized")

    # Initialize Redis pool and verify connectivity.
    pool = get_redis_pool(url=settings.redis_url)
    if await pool.ping():
        logger.info("Redis pool initialized and connection verified")
    else:
        logger.warning("Redis unavailable at startup; real-time features may be degraded")

    yield

    # -- Shutdown -------------------------------------------------------------
    shutdown_posthog()
    await pool.close()
    await engine.dispose()
    logger.info("Nexus API shut down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = get_settings()

    configure_logging(settings.log_format)
    init_sentry("nexus-api")
    init_tracing("nexus-api")
    logger.info("Configuration validated for environment=%s", settings.environment)

    app = FastAPI(
        title="AutoSwarm Nexus API",
        version="0.2.0",
        description="Core orchestration API for the AutoSwarm Office platform",
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )

    # -- Prometheus metrics ----------------------------------------------------
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    except ImportError:
        pass  # prometheus-fastapi-instrumentator not installed

    # -- CORS -----------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-CSRF-Token"],
    )

    # -- Middleware stack (outermost first) ------------------------------------
    app.add_middleware(
        SecurityHeadersMiddleware,
        cors_origins=settings.cors_origins,
        csp_extra_sources=settings.csp_extra_sources,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TenantRLSMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=settings.redis_url,
        requests_per_minute=settings.rate_limit_per_minute,
    )
    app.add_middleware(CSRFMiddleware)

    # -- Root health endpoint (K8s liveness probe) ----------------------------
    @app.get("/health", tags=["health"])
    async def root_health() -> dict[str, str]:
        return {"status": "healthy", "service": "nexus-api"}

    # -- Routers --------------------------------------------------------------
    app.include_router(health.router, prefix="/api/v1/health")
    app.include_router(agents.router, prefix="/api/v1/agents")
    app.include_router(departments.router, prefix="/api/v1/departments")
    app.include_router(approvals.router, prefix="/api/v1/approvals")
    app.include_router(swarms.router, prefix="/api/v1/swarms")
    app.include_router(billing.router, prefix="/api/v1/billing")
    app.include_router(billing_internal.router, prefix="/api/v1/billing")
    app.include_router(skills.router, prefix="/api/v1/skills")
    app.include_router(gateway.router, prefix="/api/v1/gateway")
    app.include_router(workflows.router, prefix="/api/v1/workflows")
    app.include_router(artifacts.router, prefix="/api/v1/artifacts")
    app.include_router(marketplace.router, prefix="/api/v1/marketplace")
    app.include_router(maps.router, prefix="/api/v1/maps")
    app.include_router(calendar.router, prefix="/api/v1/calendar")
    app.include_router(intelligence.router, prefix="/api/v1/intelligence")
    app.include_router(chat.router, prefix="/api/v1/chat")
    app.include_router(events.router, prefix="/api/v1/events")
    app.include_router(metrics.router, prefix="/api/v1/metrics")
    app.include_router(admin.router, prefix="/api/v1/admin")
    app.include_router(voice.router, prefix="/api/v1/voice")
    app.include_router(schedules.router, prefix="/api/v1")
    app.include_router(command_approvals.router, prefix="/api/v1")  # Gap 2: Dangerous command approval
    app.include_router(trajectories.router, prefix="/api/v1")       # Gap 6: ShareGPT trajectory export
    app.include_router(checkpoints.router, prefix="/api/v1")        # Next-tier: Session checkpoint/rollback
    app.include_router(skills_hub.router, prefix="/api/v1")         # Track D1: agentskills.io hub

    return app


# Module-level app instance for ``uvicorn nexus_api.main:app``.
app = create_app()
