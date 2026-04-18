"""Tests for the intelligence config endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from madfam_inference.org_config import ModelAssignment, OrgConfig, ProviderConfig, TaskType


class TestIntelligenceConfigEndpoint:
    """GET /api/v1/intelligence/config."""

    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_yaml(self, client, auth_headers) -> None:
        """Endpoint returns 200 with default config when no org config YAML exists."""
        with patch(
            "nexus_api.routers.intelligence.load_org_config",
            return_value=OrgConfig(),
        ):
            resp = await client.get("/api/v1/intelligence/config", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["providers"] == {}
        assert data["model_assignments"] == {}
        assert data["embedding_provider"] == "openai"
        assert data["embedding_model"] == "text-embedding-3-small"

    @pytest.mark.asyncio
    async def test_excludes_api_key_env(self, client, auth_headers) -> None:
        """Response must never include api_key_env from provider configs."""
        cfg = OrgConfig(
            providers={
                "deepinfra": ProviderConfig(
                    base_url="https://api.deepinfra.com/v1/openai",
                    api_key_env="DEEPINFRA_API_KEY",
                    vision=True,
                ),
            },
            model_assignments={
                TaskType.CODING: ModelAssignment(
                    provider="anthropic",
                    model="claude-sonnet-4-6",
                ),
            },
        )
        with patch(
            "nexus_api.routers.intelligence.load_org_config",
            return_value=cfg,
        ):
            resp = await client.get("/api/v1/intelligence/config", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()

        # Provider info present but api_key_env absent
        assert "deepinfra" in data["providers"]
        assert "api_key_env" not in data["providers"]["deepinfra"]
        assert data["providers"]["deepinfra"]["base_url"] == "https://api.deepinfra.com/v1/openai"

        # Model assignment present
        assert "coding" in data["model_assignments"]
        assert data["model_assignments"]["coding"]["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_excludes_agents(self, client, auth_headers) -> None:
        """Response must not include agent templates."""
        cfg = OrgConfig()
        with patch(
            "nexus_api.routers.intelligence.load_org_config",
            return_value=cfg,
        ):
            resp = await client.get("/api/v1/intelligence/config", headers=auth_headers)

        assert resp.status_code == 200
        assert "agents" not in resp.json()

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client) -> None:
        """Endpoint returns 401/403 without auth token."""
        resp = await client.get("/api/v1/intelligence/config")
        assert resp.status_code in (401, 403)
