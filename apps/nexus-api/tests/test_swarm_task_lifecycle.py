"""Tests for SwarmTask lifecycle: dispatch with workflow_id, PATCH with metadata."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from nexus_api.models import SwarmTask, Workflow


class TestDispatchWorkflowId:
    """POST /api/v1/swarms/dispatch persists workflow_id for custom graphs."""

    @pytest.mark.asyncio
    async def test_custom_dispatch_stores_workflow_id(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,  # type: ignore[no-untyped-def]
    ) -> None:
        """Dispatching a custom graph stores the workflow_id FK on the task."""
        wf = Workflow(
            name="Test Workflow",
            yaml_content="nodes: []",
            org_id="dev-org",
        )
        db_session.add(wf)
        await db_session.flush()
        await db_session.refresh(wf)

        with patch(
            "nexus_api.routers.swarms.get_redis_pool",
            return_value=AsyncMock(execute_with_retry=AsyncMock()),
        ):
            resp = await client.post(
                "/api/v1/swarms/dispatch",
                json={
                    "description": "Custom workflow task",
                    "graph_type": "custom",
                    "workflow_id": str(wf.id),
                },
                headers=auth_headers,
            )

        assert resp.status_code == 201
        task_id = uuid.UUID(resp.json()["id"])

        result = await db_session.execute(
            select(SwarmTask).where(SwarmTask.id == task_id)
        )
        task = result.scalar_one()
        assert task.workflow_id == wf.id

    @pytest.mark.asyncio
    async def test_non_custom_dispatch_has_null_workflow_id(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,  # type: ignore[no-untyped-def]
    ) -> None:
        """Non-custom graph types have workflow_id = None."""
        with patch(
            "nexus_api.routers.swarms.get_redis_pool",
            return_value=AsyncMock(execute_with_retry=AsyncMock()),
        ):
            resp = await client.post(
                "/api/v1/swarms/dispatch",
                json={"description": "Research task", "graph_type": "research"},
                headers=auth_headers,
            )

        assert resp.status_code == 201
        task_id = uuid.UUID(resp.json()["id"])

        result = await db_session.execute(
            select(SwarmTask).where(SwarmTask.id == task_id)
        )
        task = result.scalar_one()
        assert task.workflow_id is None


class TestPatchTaskMetadata:
    """PATCH /api/v1/swarms/tasks/{id} accepts started_at and error_message."""

    @pytest.mark.asyncio
    async def test_patch_sets_started_at(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,  # type: ignore[no-untyped-def]
    ) -> None:
        """PATCH with started_at persists the timestamp."""
        with patch(
            "nexus_api.routers.swarms.get_redis_pool",
            return_value=AsyncMock(execute_with_retry=AsyncMock()),
        ):
            create_resp = await client.post(
                "/api/v1/swarms/dispatch",
                json={"description": "Metadata test", "graph_type": "research"},
                headers=auth_headers,
            )
        task_id = uuid.UUID(create_resp.json()["id"])

        patch_resp = await client.patch(
            f"/api/v1/swarms/tasks/{task_id}",
            json={
                "status": "running",
                "started_at": "2026-03-14T10:00:00+00:00",
            },
            headers=auth_headers,
        )
        assert patch_resp.status_code == 200

        from sqlalchemy import select

        result = await db_session.execute(
            select(SwarmTask).where(SwarmTask.id == task_id)
        )
        task = result.scalar_one()
        assert task.started_at is not None

    @pytest.mark.asyncio
    async def test_patch_sets_error_message(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,  # type: ignore[no-untyped-def]
    ) -> None:
        """PATCH with error_message persists the error string."""
        with patch(
            "nexus_api.routers.swarms.get_redis_pool",
            return_value=AsyncMock(execute_with_retry=AsyncMock()),
        ):
            create_resp = await client.post(
                "/api/v1/swarms/dispatch",
                json={"description": "Error test", "graph_type": "research"},
                headers=auth_headers,
            )
        task_id = uuid.UUID(create_resp.json()["id"])

        patch_resp = await client.patch(
            f"/api/v1/swarms/tasks/{task_id}",
            json={
                "status": "failed",
                "error_message": "Timed out after 300s",
            },
            headers=auth_headers,
        )
        assert patch_resp.status_code == 200

        from sqlalchemy import select

        result = await db_session.execute(
            select(SwarmTask).where(SwarmTask.id == task_id)
        )
        task = result.scalar_one()
        assert task.error_message == "Timed out after 300s"
        assert task.completed_at is not None  # failed sets completed_at

    @pytest.mark.asyncio
    async def test_patch_without_metadata_omits_fields(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        db_session,  # type: ignore[no-untyped-def]
    ) -> None:
        """PATCH without started_at/error_message leaves them null."""
        with patch(
            "nexus_api.routers.swarms.get_redis_pool",
            return_value=AsyncMock(execute_with_retry=AsyncMock()),
        ):
            create_resp = await client.post(
                "/api/v1/swarms/dispatch",
                json={"description": "No metadata", "graph_type": "research"},
                headers=auth_headers,
            )
        task_id = uuid.UUID(create_resp.json()["id"])

        await client.patch(
            f"/api/v1/swarms/tasks/{task_id}",
            json={"status": "running"},
            headers=auth_headers,
        )

        from sqlalchemy import select

        result = await db_session.execute(
            select(SwarmTask).where(SwarmTask.id == task_id)
        )
        task = result.scalar_one()
        assert task.started_at is None
        assert task.error_message is None
