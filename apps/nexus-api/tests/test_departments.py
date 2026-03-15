"""Tests for the departments CRUD router."""

from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.mark.asyncio
class TestListDepartments:
    async def test_list_empty(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.get("/api/v1/departments/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_create(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": "Engineering", "slug": "eng"},
        )
        resp = await client.get("/api/v1/departments/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["slug"] == "eng"


@pytest.mark.asyncio
class TestCreateDepartment:
    async def test_create_success(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": "Research", "slug": "research", "max_agents": 10},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Research"
        assert data["slug"] == "research"
        assert data["max_agents"] == 10

    async def test_duplicate_slug_409(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": "D1", "slug": "dup-slug"},
        )
        resp = await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": "D2", "slug": "dup-slug"},
        )
        assert resp.status_code == 409

    async def test_invalid_slug_422(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": "Bad", "slug": "Invalid Slug!"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestGetDepartment:
    async def test_get_by_id(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        create_resp = await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": "Support", "slug": "support"},
        )
        dept_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/departments/{dept_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["slug"] == "support"
        assert "agents" in resp.json()

    async def test_get_not_found(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/departments/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestUpdateDepartment:
    async def test_update_name(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        create_resp = await client.post(
            "/api/v1/departments/",
            headers=auth_headers,
            json={"name": "Old Name", "slug": "upd-test"},
        )
        dept_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/departments/{dept_id}",
            headers=auth_headers,
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
