"""Tests for workflow template listing and creation endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# List templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_list_templates(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """GET /templates returns all 5 built-in templates."""
    resp = await client.get("/api/v1/workflows/templates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5

    filenames = {t["filename"] for t in data}
    assert filenames == {
        "3d-modeling.yaml",
        "content-marketing.yaml",
        "data-analysis.yaml",
        "devops-pipeline.yaml",
        "video-production.yaml",
    }


@pytest.mark.asyncio()
async def test_list_templates_contains_expected_fields(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Each template response includes name, description, filename, category, node_count."""
    resp = await client.get("/api/v1/workflows/templates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    for template in data:
        assert "name" in template
        assert "description" in template
        assert "filename" in template
        assert "category" in template
        assert "node_count" in template
        assert isinstance(template["node_count"], int)
        assert template["node_count"] >= 1


@pytest.mark.asyncio()
async def test_list_templates_empty_directory(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Returns empty list when templates directory does not exist."""
    with patch(
        "nexus_api.routers.workflows._TEMPLATES_DIR",
        Path("/nonexistent/path/templates"),
    ):
        resp = await client.get("/api/v1/workflows/templates", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Create from template — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_create_from_template_success(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Creating a workflow from a valid template succeeds and persists."""
    resp = await client.post(
        "/api/v1/workflows/from-template",
        json={"template_filename": "3d-modeling.yaml"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "3D Modeling Pipeline"
    assert data["yaml_content"] != ""
    assert data["id"] is not None


@pytest.mark.asyncio()
async def test_create_from_template_custom_name(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Creating from template with a custom name overrides the template name."""
    resp = await client.post(
        "/api/v1/workflows/from-template",
        json={
            "template_filename": "devops-pipeline.yaml",
            "name": "My Custom Pipeline",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "My Custom Pipeline"


# ---------------------------------------------------------------------------
# Create from template — error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_create_from_template_invalid_filename(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Filename that doesn't match the allowed pattern returns 422."""
    resp = await client.post(
        "/api/v1/workflows/from-template",
        json={"template_filename": "../etc/passwd"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio()
async def test_create_from_template_not_found(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Requesting a non-existent template returns 404."""
    resp = await client.post(
        "/api/v1/workflows/from-template",
        json={"template_filename": "nonexistent.yaml"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Template validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_template_validation(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """All built-in templates pass YAML validation."""
    list_resp = await client.get("/api/v1/workflows/templates", headers=auth_headers)
    templates = list_resp.json()
    assert len(templates) > 0

    for template in templates:
        resp = await client.post(
            "/api/v1/workflows/from-template",
            json={"template_filename": template["filename"]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, (
            f"Template {template['filename']} failed validation: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Auth requirement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_templates_require_auth(client: httpx.AsyncClient) -> None:
    """Template endpoints require authentication."""
    resp = await client.get("/api/v1/workflows/templates")
    assert resp.status_code in (401, 403)

    resp = await client.post(
        "/api/v1/workflows/from-template",
        json={"template_filename": "3d-modeling.yaml"},
    )
    assert resp.status_code in (401, 403)
