"""Tests for the billing internal router (worker-to-API metering)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
class TestRecordUsage:
    async def test_record_success(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/billing/record",
            json={"action": "inference", "amount": 100, "org_id": "default"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "recorded"

    async def test_missing_required_fields(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/billing/record",
            json={"action": "inference"},
        )
        assert resp.status_code == 422

    async def test_amount_must_be_positive(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/billing/record",
            json={"action": "inference", "amount": 0},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestCheckBudget:
    async def test_check_budget_default(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/billing/check-budget",
            json={"org_id": "default"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "daily_limit" in data
        assert "used" in data
        assert "remaining" in data
        assert "over_budget" in data
        assert data["over_budget"] is False

    async def test_budget_after_recording(self, client: httpx.AsyncClient) -> None:
        await client.post(
            "/api/v1/billing/record",
            json={"action": "inference", "amount": 50, "org_id": "budget-org"},
        )
        resp = await client.post(
            "/api/v1/billing/check-budget",
            json={"org_id": "budget-org"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["used"] == 50
