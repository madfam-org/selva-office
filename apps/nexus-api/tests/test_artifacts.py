"""Tests for the artifacts REST API endpoints.

These tests validate routing, auth, and response shapes. Full artifact CRUD
is tested via the artifact storage tests in packages/tools/tests/.
"""

from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.mark.asyncio()
async def test_list_artifacts_empty(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/artifacts", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["artifacts"] == []


@pytest.mark.asyncio()
async def test_list_artifacts_filter_by_task_id(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Filtering by task_id returns empty when no matching artifacts exist."""
    resp = await client.get(
        f"/api/v1/artifacts?task_id={uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio()
async def test_get_artifact_not_found(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get(
        f"/api/v1/artifacts/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio()
async def test_download_artifact_not_found(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get(
        f"/api/v1/artifacts/{uuid.uuid4()}/download",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio()
async def test_delete_artifact_not_found(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.delete(
        f"/api/v1/artifacts/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio()
async def test_list_artifacts_requires_auth(client: httpx.AsyncClient) -> None:
    """Artifact endpoints require authentication."""
    # Without auth headers, the request is rejected
    resp = await client.get("/api/v1/artifacts")
    assert resp.status_code in (401, 403)
