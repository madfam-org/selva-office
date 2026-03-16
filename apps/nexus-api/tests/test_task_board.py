"""Tests for the task board endpoint GET /api/v1/swarms/tasks/board."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from nexus_api.models import Agent, SwarmTask, TaskEvent

# The dev auth bypass returns org_id="dev-org".
DEV_ORG = "dev-org"
OTHER_ORG = "other-org"


async def _seed_agent(db_session, *, name: str = "Coder-Alpha", org_id: str = DEV_ORG) -> Agent:
    """Insert an agent and return it with a refreshed id."""
    agent = Agent(name=name, role="coder", status="idle", org_id=org_id)
    db_session.add(agent)
    await db_session.flush()
    await db_session.refresh(agent)
    return agent


async def _seed_task(
    db_session,
    *,
    description: str = "Task",
    graph_type: str = "coding",
    status: str = "queued",
    org_id: str = DEV_ORG,
    assigned_agent_ids: list[str] | None = None,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> SwarmTask:
    """Insert a SwarmTask with explicit field overrides."""
    task = SwarmTask(
        description=description,
        graph_type=graph_type,
        status=status,
        org_id=org_id,
        assigned_agent_ids=assigned_agent_ids or [],
    )
    if created_at is not None:
        task.created_at = created_at
    if started_at is not None:
        task.started_at = started_at
    if completed_at is not None:
        task.completed_at = completed_at
    db_session.add(task)
    await db_session.flush()
    await db_session.refresh(task)
    return task


async def _seed_event(
    db_session,
    *,
    task_id: uuid.UUID,
    duration_ms: int = 100,
    token_count: int = 50,
) -> TaskEvent:
    """Insert a TaskEvent linked to a task."""
    event = TaskEvent(
        task_id=task_id,
        event_type="node.completed",
        event_category="task",
        duration_ms=duration_ms,
        token_count=token_count,
        org_id=DEV_ORG,
    )
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    return event


@pytest.mark.asyncio
class TestTaskBoard:
    """GET /api/v1/swarms/tasks/board returns a kanban-style board response."""

    async def test_returns_200_with_columns_and_totals(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Empty board returns 200 with all four columns and zero totals."""
        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert "columns" in body
        assert "totals" in body

    async def test_response_has_four_status_columns(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """The board always has queued, running, completed, and failed columns."""
        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)

        columns = resp.json()["columns"]
        assert set(columns.keys()) == {"queued", "running", "completed", "failed"}

    async def test_task_board_item_has_required_fields(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,
    ) -> None:
        """Each item in a column contains all TaskBoardItem fields."""
        await _seed_task(db_session, description="Field check", status="running")
        await db_session.commit()

        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)

        items = resp.json()["columns"]["running"]
        assert len(items) == 1
        item = items[0]

        required_keys = {
            "id",
            "description",
            "graph_type",
            "status",
            "agent_names",
            "created_at",
            "started_at",
            "completed_at",
            "duration_ms",
            "total_tokens",
            "event_count",
        }
        assert required_keys.issubset(item.keys())
        assert item["description"] == "Field check"
        assert item["status"] == "running"
        assert item["graph_type"] == "coding"

    async def test_totals_match_column_counts(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,
    ) -> None:
        """The totals dict mirrors the length of each column list."""
        await _seed_task(db_session, description="Q1", status="queued")
        await _seed_task(db_session, description="Q2", status="pending")
        await _seed_task(db_session, description="R1", status="running")
        await _seed_task(db_session, description="C1", status="completed")
        await _seed_task(db_session, description="C2", status="completed")
        await _seed_task(db_session, description="F1", status="failed")
        await _seed_task(db_session, description="F2", status="cancelled")
        await db_session.commit()

        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)
        body = resp.json()

        for col_name, items in body["columns"].items():
            assert body["totals"][col_name] == len(items), (
                f"totals[{col_name}]={body['totals'][col_name]} != len(items)={len(items)}"
            )

        # Verify the mapped counts: pending maps to queued, cancelled maps to failed.
        assert body["totals"]["queued"] == 2
        assert body["totals"]["running"] == 1
        assert body["totals"]["completed"] == 2
        assert body["totals"]["failed"] == 2

    async def test_agent_names_resolved_from_ids(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,
    ) -> None:
        """Agent UUIDs in assigned_agent_ids are resolved to human-readable names."""
        agent = await _seed_agent(db_session, name="Coder-Alpha")
        await _seed_task(
            db_session,
            description="Named task",
            status="running",
            assigned_agent_ids=[str(agent.id)],
        )
        await db_session.commit()

        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)

        items = resp.json()["columns"]["running"]
        assert len(items) == 1
        assert "Coder-Alpha" in items[0]["agent_names"]

    async def test_event_aggregates_included(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,
    ) -> None:
        """TaskEvent aggregates (duration_ms, total_tokens, event_count) appear on items."""
        task = await _seed_task(db_session, description="Evented task", status="completed")
        await _seed_event(db_session, task_id=task.id, duration_ms=200, token_count=100)
        await _seed_event(db_session, task_id=task.id, duration_ms=300, token_count=150)
        await db_session.commit()

        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)

        items = resp.json()["columns"]["completed"]
        assert len(items) == 1
        item = items[0]

        assert item["event_count"] == 2
        assert item["duration_ms"] == 500
        assert item["total_tokens"] == 250

    async def test_tasks_ordered_by_created_at_descending(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,
    ) -> None:
        """Within a column, tasks appear newest-first (created_at DESC)."""
        now = datetime.now(UTC)
        await _seed_task(
            db_session,
            description="Old task",
            status="queued",
            created_at=now - timedelta(hours=2),
        )
        await _seed_task(
            db_session,
            description="New task",
            status="queued",
            created_at=now,
        )
        await _seed_task(
            db_session,
            description="Mid task",
            status="queued",
            created_at=now - timedelta(hours=1),
        )
        await db_session.commit()

        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)

        items = resp.json()["columns"]["queued"]
        descriptions = [item["description"] for item in items]
        assert descriptions == ["New task", "Mid task", "Old task"]

    async def test_board_respects_org_id_tenant_scoping(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,
    ) -> None:
        """Tasks from a different org_id are invisible to the current tenant."""
        await _seed_task(db_session, description="My task", status="running", org_id=DEV_ORG)
        await _seed_task(db_session, description="Their task", status="running", org_id=OTHER_ORG)
        await db_session.commit()

        resp = await client.get("/api/v1/swarms/tasks/board", headers=auth_headers)
        body = resp.json()

        # The dev auth bypass yields org_id="dev-org", so only that task is visible.
        all_descriptions: list[str] = []
        for items in body["columns"].values():
            all_descriptions.extend(item["description"] for item in items)

        assert "My task" in all_descriptions
        assert "Their task" not in all_descriptions
        assert body["totals"]["running"] == 1
