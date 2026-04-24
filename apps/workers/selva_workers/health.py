"""Worker health server with Prometheus metrics endpoint."""

from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

# Prometheus metrics (optional dependency)
try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    REGISTRY = CollectorRegistry()
    TASK_PROCESSING_SECONDS = Histogram(
        "task_processing_seconds",
        "Time spent processing tasks",
        ["graph_type"],
        registry=REGISTRY,
    )
    TASK_TOTAL = Counter(
        "task_total",
        "Total tasks processed",
        ["graph_type", "status"],
        registry=REGISTRY,
    )
    WORKER_CURRENT_TASK = Gauge(
        "worker_current_task",
        "Whether the worker is currently processing a task",
        registry=REGISTRY,
    )
    QUEUE_CONNECTED = Gauge(
        "queue_connected",
        "Whether the worker is connected to the task queue",
        registry=REGISTRY,
    )
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False
    REGISTRY = None  # type: ignore[assignment]


class WorkerHealth:
    """Lightweight HTTP server for health checks and Prometheus metrics.

    Runs on a configurable port (default 4305) alongside the main worker loop.
    """

    def __init__(self, port: int = 4305) -> None:
        self.port = port
        self._current_task: str | None = None
        self._current_graph_type: str | None = None
        self._last_completed_at: float | None = None
        self._tasks_processed: int = 0
        self._tasks_failed: int = 0
        self._queue_connected: bool = False
        self._started_at: float = time.time()
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        """Start the health HTTP server as a background task."""
        app = web.Application()
        app.router.add_get("/health", self._health_handler)
        app.router.add_get("/metrics", self._metrics_handler)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("Worker health server listening on port %d", self.port)

    async def stop(self) -> None:
        """Stop the health HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    def on_task_start(self, task_id: str, graph_type: str) -> None:
        """Record that a task has started processing."""
        self._current_task = task_id
        self._current_graph_type = graph_type
        if _HAS_PROMETHEUS:
            WORKER_CURRENT_TASK.set(1)

    def on_task_complete(self, task_id: str, graph_type: str) -> None:
        """Record that a task has completed successfully."""
        self._current_task = None
        self._current_graph_type = None
        self._last_completed_at = time.time()
        self._tasks_processed += 1
        if _HAS_PROMETHEUS:
            WORKER_CURRENT_TASK.set(0)
            TASK_TOTAL.labels(graph_type=graph_type, status="success").inc()

    def on_task_error(self, task_id: str, graph_type: str) -> None:
        """Record that a task has failed."""
        self._current_task = None
        self._current_graph_type = None
        self._tasks_failed += 1
        if _HAS_PROMETHEUS:
            WORKER_CURRENT_TASK.set(0)
            TASK_TOTAL.labels(graph_type=graph_type, status="error").inc()

    def on_queue_connected(self, connected: bool) -> None:
        """Record queue connection state."""
        self._queue_connected = connected
        if _HAS_PROMETHEUS:
            QUEUE_CONNECTED.set(1 if connected else 0)

    def task_timer(self, graph_type: str) -> Any:
        """Return a context manager for timing task processing."""
        if _HAS_PROMETHEUS:
            return TASK_PROCESSING_SECONDS.labels(graph_type=graph_type).time()

        class _NoopTimer:
            def __enter__(self) -> _NoopTimer:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        return _NoopTimer()

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Health endpoint returning worker status."""
        data = {
            "status": "healthy",
            "service": "worker",
            "current_task": self._current_task,
            "current_graph_type": self._current_graph_type,
            "last_completed_at": self._last_completed_at,
            "tasks_processed": self._tasks_processed,
            "tasks_failed": self._tasks_failed,
            "queue_connected": self._queue_connected,
            "uptime_seconds": round(time.time() - self._started_at, 1),
        }
        return web.json_response(data)

    async def _metrics_handler(self, request: web.Request) -> web.Response:
        """Prometheus metrics endpoint."""
        if _HAS_PROMETHEUS and REGISTRY is not None:
            body = generate_latest(REGISTRY)
            return web.Response(body=body, content_type="text/plain; version=0.0.4")
        return web.Response(text="# prometheus-client not installed\n", content_type="text/plain")
