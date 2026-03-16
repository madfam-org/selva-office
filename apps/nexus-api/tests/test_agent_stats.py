"""Tests for agent performance stats PATCH endpoint (PR 1: Agent Learning Loop)."""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture()
async def _seed_agent(client, auth_headers):
    """Create an agent and return its ID."""
    resp = await client.post(
        "/api/v1/agents/",
        json={"name": "TestBot", "role": "coder"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestAgentStatsEndpoint:
    """PATCH /api/v1/agents/{id}/stats delta increment tests."""

    @pytest.mark.asyncio
    async def test_increment_tasks_completed(self, client, auth_headers, _seed_agent) -> None:
        agent_id = _seed_agent
        resp = await client.patch(
            f"/api/v1/agents/{agent_id}/stats",
            json={"tasks_completed_delta": 1, "task_duration_seconds": 42.5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks_completed"] == 1
        assert data["tasks_failed"] == 0
        assert data["avg_task_duration_seconds"] == pytest.approx(42.5)
        assert data["last_task_at"] is not None

    @pytest.mark.asyncio
    async def test_increment_tasks_failed(self, client, auth_headers, _seed_agent) -> None:
        agent_id = _seed_agent
        resp = await client.patch(
            f"/api/v1/agents/{agent_id}/stats",
            json={"tasks_failed_delta": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks_failed"] == 1
        assert data["tasks_completed"] == 0

    @pytest.mark.asyncio
    async def test_running_average_duration(self, client, auth_headers, _seed_agent) -> None:
        agent_id = _seed_agent
        # First task: 10s
        await client.patch(
            f"/api/v1/agents/{agent_id}/stats",
            json={"tasks_completed_delta": 1, "task_duration_seconds": 10.0},
            headers=auth_headers,
        )
        # Second task: 20s -> avg should be 15s
        resp = await client.patch(
            f"/api/v1/agents/{agent_id}/stats",
            json={"tasks_completed_delta": 1, "task_duration_seconds": 20.0},
            headers=auth_headers,
        )
        data = resp.json()
        assert data["tasks_completed"] == 2
        assert data["avg_task_duration_seconds"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_zero_delta_noop(self, client, auth_headers, _seed_agent) -> None:
        agent_id = _seed_agent
        resp = await client.patch(
            f"/api/v1/agents/{agent_id}/stats",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks_completed"] == 0
        assert data["tasks_failed"] == 0
        assert data["last_task_at"] is None

    @pytest.mark.asyncio
    async def test_404_for_missing_agent(self, client, auth_headers) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.patch(
            f"/api/v1/agents/{fake_id}/stats",
            json={"tasks_completed_delta": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approval_counters(self, client, auth_headers, _seed_agent) -> None:
        agent_id = _seed_agent
        resp = await client.patch(
            f"/api/v1/agents/{agent_id}/stats",
            json={"approval_success_delta": 3, "approval_denial_delta": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approval_success_count"] == 3
        assert data["approval_denial_count"] == 1

    @pytest.mark.asyncio
    async def test_response_includes_performance_fields(
        self, client, auth_headers, _seed_agent,
    ) -> None:
        """GET /agents/{id} should include the new performance fields."""
        agent_id = _seed_agent
        resp = await client.get(
            f"/api/v1/agents/{agent_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks_completed" in data
        assert "tasks_failed" in data
        assert "approval_success_count" in data
        assert "approval_denial_count" in data
        assert "avg_task_duration_seconds" in data
        assert "last_task_at" in data
