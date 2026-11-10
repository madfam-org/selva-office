"""Read-only platform reads under the strict, FORCEd RLS of migration 0028.

Two read-only paths count every org's rows: the ``/metrics`` DB gauges
(``operational_metrics._refresh_db_gauges``) and the ``worker_in_flight`` count
of ``GET /api/v1/health/queue-stats``. Both used ``admin_session()``. Without
``DATABASE_ADMIN_URL`` that helper falls back to the regular pool with no
``app.current_org_id``, and the FORCEd policies hide every ``swarm_tasks`` and
``deployment_evidence_records`` row: the gauges and the count read 0. They now
read in ``tenant_session("platform")``, the marker the policies admit.

The SQLite tests cover the queries, the marker and the absent and error paths.
``TestForcedRlsOnPostgres`` proves the RLS context on a real Postgres; it runs
when ``SELVA_RLS_TEST_DATABASE_URL`` names a throwaway database reachable as a
role that can create roles (CI's test-py job sets it). It creates its own
schema and login role and drops both.
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from nexus_api import database, operational_metrics
from nexus_api.models import DeploymentEvidenceRecord, SwarmTask, SwarmTaskOutbox
from nexus_api.routers import health

OLD = datetime.now(UTC) - timedelta(hours=2)
NEW = datetime.now(UTC)


def _gauge(name: str, labels: dict[str, str] | None = None) -> float | None:
    return REGISTRY.get_sample_value(name, labels or {})


def _gauges() -> dict[str, float | None]:
    return {
        "pending": _gauge("selva_swarm_task_outbox_depth", {"status": "pending"}),
        "retryable": _gauge("selva_swarm_task_outbox_depth", {"status": "retryable"}),
        "stale": _gauge("selva_swarm_task_outbox_stale_rows"),
        "missing_evidence": _gauge("selva_production_deployment_missing_evidence_rows"),
    }


# Two orgs, so a read scoped to one org (or to none) cannot pass for the platform read.
EXPECTED_GAUGES = {"pending": 2.0, "retryable": 1.0, "stale": 2.0, "missing_evidence": 2.0}
EXPECTED_IN_FLIGHT = 3


def _seed_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(swarm_tasks, deployment_evidence_records, swarm_task_outbox) rows."""
    t = {name: uuid.uuid4() for name in ("a_prod", "b_prod", "b_prod_ok", "a_stage", "a_run")}
    tasks = [
        # Production deployments without evidence: one per org -> 2.
        {
            "id": t["a_prod"],
            "org_id": "org-a",
            "graph_type": "deployment",
            "status": "completed",
            "payload": {"environment": "production"},
        },
        {
            "id": t["b_prod"],
            "org_id": "org-b",
            "graph_type": "deployment",
            "status": "failed",
            "payload": {"target_environment": "production"},
        },
        # Has evidence: not counted.
        {
            "id": t["b_prod_ok"],
            "org_id": "org-b",
            "graph_type": "deployment",
            "status": "completed",
            "payload": {"environment": "production"},
        },
        # Staging, still queued: counted in flight, not as missing evidence.
        {
            "id": t["a_stage"],
            "org_id": "org-a",
            "graph_type": "deployment",
            "status": "queued",
            "payload": {"environment": "staging"},
        },
        # In flight in both orgs: queued (above) + pending + running -> 3.
        {
            "id": t["a_run"],
            "org_id": "org-a",
            "graph_type": "research",
            "status": "running",
            "payload": {},
        },
        {
            "id": uuid.uuid4(),
            "org_id": "org-b",
            "graph_type": "research",
            "status": "pending",
            "payload": {},
        },
    ]
    evidence = [{"id": uuid.uuid4(), "task_id": t["b_prod_ok"], "org_id": "org-b"}]
    outbox = [
        # pending: 2 (one stale), retryable: 1 (stale), sent: ignored.
        {
            "id": uuid.uuid4(),
            "task_id": t["a_stage"],
            "org_id": "org-a",
            "status": "pending",
            "next_attempt_at": None,
            "created_at": OLD,
        },
        {
            "id": uuid.uuid4(),
            "task_id": t["a_run"],
            "org_id": "org-a",
            "status": "pending",
            "next_attempt_at": None,
            "created_at": NEW,
        },
        {
            "id": uuid.uuid4(),
            "task_id": t["b_prod"],
            "org_id": "org-b",
            "status": "retryable",
            "next_attempt_at": OLD,
            "created_at": OLD,
        },
        {
            "id": uuid.uuid4(),
            "task_id": t["b_prod_ok"],
            "org_id": "org-b",
            "status": "sent",
            "next_attempt_at": None,
            "created_at": OLD,
        },
    ]
    return tasks, evidence, outbox


def _fake_redis_pool() -> MagicMock:
    client = MagicMock()
    client.xlen = AsyncMock(return_value=5)
    client.xinfo_groups = AsyncMock(
        return_value=[{"name": "workers", "consumers": 1, "pending": 4}]
    )
    pool = MagicMock()
    pool.client = AsyncMock(return_value=client)
    pool.metrics = MagicMock(return_value={})
    return pool


async def _queue_stats() -> dict[str, object]:
    with patch.object(health, "get_redis_pool", return_value=_fake_redis_pool()):
        return await health.queue_stats()


def _spy_tenant_session(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[str]:
    """Record every org ``module.tenant_session`` is opened with.

    ``health`` imports ``tenant_session`` from ``..database`` at call time, so
    its target is the ``database`` module.
    """
    orgs: list[str] = []
    real = database.tenant_session

    @asynccontextmanager
    async def spy(org_id: str) -> Any:
        orgs.append(org_id)
        async with real(org_id) as db:
            yield db

    monkeypatch.setattr(module, "tenant_session", spy)
    return orgs


def _broken_tenant_session(monkeypatch: pytest.MonkeyPatch, module: Any) -> None:
    @asynccontextmanager
    async def down(_org_id: str) -> Any:
        raise OperationalError("SELECT 1", {}, ConnectionError("db down"))
        yield  # pragma: no cover

    monkeypatch.setattr(module, "tenant_session", down)


class TestOperationalMetricsGauges:
    async def test_counts_every_org(self, db_session: AsyncSession) -> None:
        tasks, evidence, outbox = _seed_rows()
        db_session.add_all([SwarmTask(description="t", assigned_agent_ids=[], **r) for r in tasks])
        await db_session.flush()
        db_session.add_all(
            [
                DeploymentEvidenceRecord(graph_type="deployment", deployment_status="ok", **r)
                for r in evidence
            ]
        )
        db_session.add_all([SwarmTaskOutbox(payload={}, **r) for r in outbox])
        await db_session.commit()

        await operational_metrics._refresh_db_gauges()
        assert _gauges() == EXPECTED_GAUGES

    async def test_no_rows_is_a_real_zero(self) -> None:
        await operational_metrics._refresh_db_gauges()
        assert _gauges() == {
            "pending": 0.0,
            "retryable": 0.0,
            "stale": 0.0,
            "missing_evidence": 0.0,
        }

    async def test_reads_through_the_platform_rls_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orgs = _spy_tenant_session(monkeypatch, operational_metrics)
        assert not hasattr(operational_metrics, "admin_session")
        await operational_metrics._refresh_db_gauges()
        assert orgs == ["platform"]

    async def test_database_error_fails_metrics_visibly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _broken_tenant_session(monkeypatch, operational_metrics)
        with pytest.raises(OperationalError):
            await operational_metrics.render_prometheus_metrics()


class TestQueueStatsInFlight:
    async def test_counts_every_org(self, db_session: AsyncSession) -> None:
        tasks, _evidence, _outbox = _seed_rows()
        db_session.add_all([SwarmTask(description="t", assigned_agent_ids=[], **r) for r in tasks])
        await db_session.commit()

        stats = await _queue_stats()
        assert stats["worker_in_flight"] == EXPECTED_IN_FLIGHT
        assert stats["pending_total"] == 4

    async def test_no_tasks_is_a_real_zero(self) -> None:
        assert (await _queue_stats())["worker_in_flight"] == 0

    async def test_reads_through_the_platform_rls_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orgs = _spy_tenant_session(monkeypatch, database)
        await _queue_stats()
        assert orgs == ["platform"]

    async def test_database_error_falls_back_to_the_redis_pending_total(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # health imports tenant_session lazily from ..database at call time.
        _broken_tenant_session(monkeypatch, database)
        stats = await _queue_stats()
        assert stats["worker_in_flight"] == 4
        assert "error" not in stats


_PG_URL = os.environ.get("SELVA_RLS_TEST_DATABASE_URL", "")

_POLICY = (
    "CREATE POLICY tenant_isolation_{table} ON {schema}.{table} FOR ALL "
    "USING (current_setting('app.current_org_id', true) = 'platform' "
    "OR org_id = current_setting('app.current_org_id', true)) "
    "WITH CHECK (current_setting('app.current_org_id', true) = 'platform' "
    "OR org_id = current_setting('app.current_org_id', true))"
)


@pytest.mark.skipif(not _PG_URL, reason="SELVA_RLS_TEST_DATABASE_URL not set")
class TestForcedRlsOnPostgres:
    async def test_platform_marker_sees_every_org_where_the_admin_fallback_sees_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = make_url(_PG_URL).set(drivername="postgresql+asyncpg")
        suffix = uuid.uuid4().hex[:12]
        schema = role = f"platformreads_{suffix}"
        password = uuid.uuid4().hex
        owner = create_async_engine(base, poolclass=NullPool)
        tasks, evidence, outbox = _seed_rows()
        try:
            async with owner.begin() as conn:
                await conn.execute(text(f"CREATE SCHEMA {schema}"))
                # Same shape as the app role: no superuser, no BYPASSRLS, and it
                # owns the tables (FORCE is what stops the owner bypass).
                await conn.execute(
                    text(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS")
                )
                # Only the columns these reads touch.
                await conn.execute(
                    text(
                        f"CREATE TABLE {schema}.swarm_tasks ("
                        "id uuid PRIMARY KEY, org_id varchar(255) NOT NULL, "
                        "graph_type varchar(50) NOT NULL, status varchar(50) NOT NULL, "
                        "payload jsonb NOT NULL)"
                    )
                )
                await conn.execute(
                    text(
                        f"CREATE TABLE {schema}.deployment_evidence_records ("
                        "id uuid PRIMARY KEY, task_id uuid NOT NULL, "
                        "org_id varchar(255) NOT NULL)"
                    )
                )
                await conn.execute(
                    text(
                        f"CREATE TABLE {schema}.swarm_task_outbox ("
                        "id uuid PRIMARY KEY, task_id uuid NOT NULL, "
                        "org_id varchar(255) NOT NULL, status varchar(16) NOT NULL, "
                        "next_attempt_at timestamptz, created_at timestamptz NOT NULL)"
                    )
                )
                for r in tasks:
                    await conn.execute(
                        text(
                            f"INSERT INTO {schema}.swarm_tasks VALUES "
                            "(:id, :org_id, :graph_type, :status, CAST(:payload AS jsonb))"
                        ),
                        {**r, "payload": json.dumps(r["payload"])},
                    )
                for r in evidence:
                    await conn.execute(
                        text(
                            f"INSERT INTO {schema}.deployment_evidence_records "
                            "VALUES (:id, :task_id, :org_id)"
                        ),
                        r,
                    )
                for r in outbox:
                    await conn.execute(
                        text(
                            f"INSERT INTO {schema}.swarm_task_outbox VALUES "
                            "(:id, :task_id, :org_id, :status, :next_attempt_at, :created_at)"
                        ),
                        r,
                    )
                # Migrations 0028 (swarm_tasks) and 0034 (deployment evidence):
                # the strict policy, verbatim, then FORCE. The outbox (0033) has
                # no policy in the migrations, so it has none here either.
                for table in ("swarm_tasks", "deployment_evidence_records"):
                    await conn.execute(
                        text(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")
                    )
                    await conn.execute(text(_POLICY.format(table=table, schema=schema)))
                    await conn.execute(
                        text(f"ALTER TABLE {schema}.{table} FORCE ROW LEVEL SECURITY")
                    )
                await conn.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO {role}"))
                for table in ("swarm_tasks", "deployment_evidence_records", "swarm_task_outbox"):
                    await conn.execute(text(f"ALTER TABLE {schema}.{table} OWNER TO {role}"))

            app = create_async_engine(
                base.set(username=role, password=password),
                poolclass=NullPool,
                connect_args={"server_settings": {"search_path": schema}},
            )
            factory = async_sessionmaker(app, class_=AsyncSession, expire_on_commit=False)
            monkeypatch.setattr(database, "get_session_factory", lambda: factory)
            # What admin_session() is in production: no DATABASE_ADMIN_URL, so
            # the admin factory is the regular pool.
            monkeypatch.setattr(database, "get_admin_session_factory", lambda: factory)
            try:
                async with database.admin_session() as db:
                    hidden = (
                        await db.execute(text("SELECT count(*) FROM swarm_tasks"))
                    ).scalar_one()
                assert hidden == 0  # the bug: every row hidden

                await operational_metrics._refresh_db_gauges()
                assert _gauges() == EXPECTED_GAUGES

                assert (await _queue_stats())["worker_in_flight"] == EXPECTED_IN_FLIGHT

                async with database.tenant_session("org-a") as db:
                    org_a = (
                        await db.execute(text("SELECT count(*) FROM swarm_tasks"))
                    ).scalar_one()
                assert org_a == 3  # tenants stay isolated
            finally:
                await app.dispose()
        finally:
            async with owner.begin() as conn:
                await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
                await conn.execute(text(f"DROP ROLE IF EXISTS {role}"))
            await owner.dispose()
