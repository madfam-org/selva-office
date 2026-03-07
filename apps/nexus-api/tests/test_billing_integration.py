"""Tests for billing integration: internal endpoints, budget checks, Dhanam webhook tier."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


class TestBillingRecord:
    """POST /api/v1/billing/record writes a ledger entry."""

    @pytest.mark.asyncio
    async def test_records_usage(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.post(
            "/api/v1/billing/record",
            json={
                "action": "inference",
                "amount": 150,
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "org_id": "test-org",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "recorded"

    @pytest.mark.asyncio
    async def test_rejects_zero_amount(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/billing/record",
            json={"action": "inference", "amount": 0, "org_id": "test-org"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_records_with_agent_and_task_ids(
        self, client: httpx.AsyncClient
    ) -> None:
        import uuid

        agent_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        resp = await client.post(
            "/api/v1/billing/record",
            json={
                "action": "inference",
                "amount": 50,
                "agent_id": agent_id,
                "task_id": task_id,
                "org_id": "dev",
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_records_with_provider_and_model(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/billing/record",
            json={
                "action": "inference",
                "amount": 100,
                "provider": "openai",
                "model": "gpt-4o",
                "org_id": "dev",
            },
        )
        assert resp.status_code == 201


class TestCheckBudget:
    """POST /api/v1/billing/check-budget returns budget status."""

    @pytest.mark.asyncio
    async def test_returns_budget_when_under_limit(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/billing/check-budget",
            json={"org_id": "dev"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["over_budget"] is False
        assert data["remaining"] > 0
        assert "daily_limit" in data

    @pytest.mark.asyncio
    async def test_shows_over_budget_after_heavy_usage(
        self, client: httpx.AsyncClient
    ) -> None:
        # Record enough usage to exceed the default 1000 limit
        for _ in range(11):
            await client.post(
                "/api/v1/billing/record",
                json={"action": "inference", "amount": 100, "org_id": "budget-test"},
            )

        resp = await client.post(
            "/api/v1/billing/check-budget",
            json={"org_id": "budget-test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["over_budget"] is True
        assert data["remaining"] == 0


class TestDispatchBudgetCheck:
    """Dispatch rejects with 402 when over budget."""

    @pytest.mark.asyncio
    async def test_dispatch_rejected_when_over_budget(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Fill up the budget for "dev-org" (the org_id from dev auth bypass)
        for _ in range(101):
            await client.post(
                "/api/v1/billing/record",
                json={"action": "inference", "amount": 10, "org_id": "dev-org"},
            )

        resp = await client.post(
            "/api/v1/swarms/dispatch",
            json={"description": "Over budget task", "graph_type": "research"},
            headers=auth_headers,
        )
        assert resp.status_code == 402


class TestDhanamWebhookTier:
    """Dhanam webhook updates cached tier limits."""

    @pytest.mark.asyncio
    async def test_subscription_updated_caches_tier(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        import hashlib
        import hmac
        import json

        payload = {
            "type": "subscription.updated",
            "data": {"tier": "professional", "org_id": "acme-corp"},
        }
        body = json.dumps(payload).encode()

        # Mock Redis to capture the set call
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with (
            patch(
                "nexus_api.routers.billing.get_settings",
                return_value=type(
                    "S", (), {"dhanam_webhook_secret": "", "redis_url": "redis://x"}
                )(),
            ),
            patch(
                "redis.asyncio.from_url",
                return_value=mock_redis,
            ),
        ):
            resp = await client.post(
                "/api/v1/billing/webhooks/dhanam",
                content=body,
                headers={**auth_headers, "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        mock_redis.set.assert_called_once_with(
            "autoswarm:tier:acme-corp", "5000", ex=86400
        )
