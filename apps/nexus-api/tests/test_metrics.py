"""Tests for the metrics dashboard API at /api/v1/metrics/dashboard."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.models import (
    Agent,
    ApprovalRequest,
    ComputeTokenLedger,
    Department,
    SwarmTask,
    TaskEvent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(UTC)


def _make_department(org_id: str = "dev-org") -> Department:
    return Department(
        id=uuid.uuid4(),
        name="Engineering",
        slug=f"dept-eng-{uuid.uuid4().hex[:8]}",
        org_id=org_id,
    )


def _make_agent(department_id: uuid.UUID, org_id: str = "dev-org") -> Agent:
    return Agent(
        id=uuid.uuid4(),
        name=f"Agent-{uuid.uuid4().hex[:6]}",
        role="coder",
        status="idle",
        department_id=department_id,
        org_id=org_id,
    )


async def _seed_metrics_data(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Insert a minimal but representative set of rows across all metric tables.

    Returns a dict of useful IDs for assertions.
    """
    dept = _make_department()
    db.add(dept)
    await db.flush()

    agent = _make_agent(dept.id)
    db.add(agent)
    await db.flush()

    now = _utcnow()

    # -- SwarmTasks (3 completed, 1 failed, 1 pending) -------------------------
    for i, status in enumerate(["completed", "completed", "completed", "failed", "pending"]):
        started = now - timedelta(minutes=30 + i * 5)
        completed = started + timedelta(minutes=10) if status == "completed" else None
        task = SwarmTask(
            id=uuid.uuid4(),
            description=f"Test task {i}",
            graph_type="coding",
            status=status,
            assigned_agent_ids=[str(agent.id)],
            org_id="dev-org",
            created_at=now - timedelta(minutes=60 - i),
            started_at=started,
            completed_at=completed,
        )
        db.add(task)
    await db.flush()

    # -- TaskEvents (node events for utilization + error events) ---------------
    for i in range(4):
        db.add(TaskEvent(
            id=uuid.uuid4(),
            event_type="node.completed",
            event_category="node",
            agent_id=agent.id,
            duration_ms=5000,
            org_id="dev-org",
            created_at=now - timedelta(minutes=20 + i),
        ))

    # Two error events
    error_event_id = uuid.uuid4()
    for i, etype in enumerate(["task.failed", "node.error"]):
        db.add(TaskEvent(
            id=error_event_id if i == 0 else uuid.uuid4(),
            event_type=etype,
            event_category="task" if "task" in etype else "node",
            agent_id=agent.id,
            node_id=f"error-node-{i}",
            error_message=f"Something went wrong #{i}",
            org_id="dev-org",
            created_at=now - timedelta(minutes=5 + i),
        ))
    await db.flush()

    # -- ApprovalRequests (2 resolved, 1 pending) ------------------------------
    for i in range(2):
        created = now - timedelta(minutes=40 + i * 10)
        db.add(ApprovalRequest(
            id=uuid.uuid4(),
            agent_id=agent.id,
            action_category="file_write",
            action_type="write",
            status="approved",
            created_at=created,
            responded_at=created + timedelta(seconds=45),
            org_id="dev-org",
        ))
    db.add(ApprovalRequest(
        id=uuid.uuid4(),
        agent_id=agent.id,
        action_category="file_write",
        action_type="write",
        status="pending",
        created_at=now - timedelta(minutes=2),
        org_id="dev-org",
    ))
    await db.flush()

    # -- ComputeTokenLedger entries --------------------------------------------
    for provider, model, amount in [
        ("openai", "gpt-4o", 1500),
        ("openai", "gpt-4o", 800),
        ("anthropic", "claude-sonnet-4-20250514", 2200),
    ]:
        db.add(ComputeTokenLedger(
            id=uuid.uuid4(),
            action="inference",
            amount=amount,
            agent_id=agent.id,
            provider=provider,
            model=model,
            org_id="dev-org",
            created_at=now - timedelta(minutes=15),
        ))
    await db.flush()
    await db.commit()

    return {"agent_id": agent.id, "dept_id": dept.id, "error_event_id": error_event_id}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMetricsDashboard:
    """GET /api/v1/metrics/dashboard."""

    # -- 1. Default period (24h) returns 200 -----------------------------------

    async def test_default_period_returns_200(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "24h"

    # -- 2. Valid short period (1h) --------------------------------------------

    async def test_period_1h(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get(
            "/api/v1/metrics/dashboard",
            params={"period": "1h"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["period"] == "1h"

    # -- 3. Valid long period (7d) ---------------------------------------------

    async def test_period_7d(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get(
            "/api/v1/metrics/dashboard",
            params={"period": "7d"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["period"] == "7d"

    # -- 4. Valid longest period (30d) -----------------------------------------

    async def test_period_30d(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get(
            "/api/v1/metrics/dashboard",
            params={"period": "30d"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["period"] == "30d"

    # -- 5. Invalid period returns 422 -----------------------------------------

    async def test_invalid_period_returns_422(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        resp = await client.get(
            "/api/v1/metrics/dashboard",
            params={"period": "invalid"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    # -- 6. Response includes agent_utilization_pct ----------------------------

    async def test_response_includes_agent_utilization_pct(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        data = resp.json()
        assert "agent_utilization_pct" in data
        assert isinstance(data["agent_utilization_pct"], (int, float))
        assert 0.0 <= data["agent_utilization_pct"] <= 100.0

    # -- 7. Response includes task_throughput with status_counts ----------------

    async def test_response_includes_task_throughput(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        data = resp.json()
        throughput = data["task_throughput"]
        assert "status_counts" in throughput
        assert "total" in throughput
        assert "avg_duration_s" in throughput
        assert isinstance(throughput["status_counts"], dict)
        assert throughput["total"] >= 5  # seeded 5 tasks
        assert "completed" in throughput["status_counts"]
        assert throughput["status_counts"]["completed"] == 3

    # -- 8. Response includes approval_latency with avg_seconds ----------------

    async def test_response_includes_approval_latency(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        data = resp.json()
        latency = data["approval_latency"]
        assert "avg_seconds" in latency
        assert "resolved_count" in latency
        assert "pending_count" in latency
        assert latency["resolved_count"] == 2
        assert latency["pending_count"] == 1

    # -- 9. Response includes cost_breakdown as array --------------------------

    async def test_response_includes_cost_breakdown(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        data = resp.json()
        cost = data["cost_breakdown"]
        assert isinstance(cost, list)
        assert len(cost) >= 2  # openai/gpt-4o and anthropic/claude
        providers = {entry["provider"] for entry in cost}
        assert "openai" in providers
        assert "anthropic" in providers
        for entry in cost:
            assert "provider" in entry
            assert "model" in entry
            assert "total_tokens" in entry
            assert "call_count" in entry

    # -- 10. Response includes error_rate as number ----------------------------

    async def test_response_includes_error_rate(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        data = resp.json()
        assert "error_rate" in data
        assert isinstance(data["error_rate"], (int, float))
        # We seeded 2 error events out of 6 total events, so rate should be > 0
        assert data["error_rate"] > 0

    # -- 11. Response includes trends with tasks and errors arrays -------------

    async def test_response_includes_trends(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        data = resp.json()
        trends = data["trends"]
        assert "tasks" in trends
        assert "errors" in trends
        assert isinstance(trends["tasks"], list)
        assert isinstance(trends["errors"], list)
        # Each trend point should have timestamp and value
        for point in trends["tasks"]:
            assert "timestamp" in point
            assert "value" in point
        for point in trends["errors"]:
            assert "timestamp" in point
            assert "value" in point

    # -- 12. Response includes recent_errors as array --------------------------

    async def test_response_includes_recent_errors(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        await _seed_metrics_data(db_session)
        resp = await client.get("/api/v1/metrics/dashboard", headers=auth_headers)
        data = resp.json()
        errors = data["recent_errors"]
        assert isinstance(errors, list)
        assert len(errors) == 2  # seeded 2 error events
        for err in errors:
            assert "id" in err
            assert "event_type" in err
            assert "error_message" in err
            assert "created_at" in err
        event_types = {e["event_type"] for e in errors}
        assert event_types == {"task.failed", "node.error"}
