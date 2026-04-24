"""Tests for the HITL-confidence router (Sprint 1 — observe only).

Covers:
    POST /api/v1/hitl/decisions        — auth + recording + bucket rollup
    GET  /api/v1/hitl/confidence       — dashboard with filters
    GET  /api/v1/hitl/decisions        — decision list with filters

Hits the in-memory SQLite from conftest.py — no DB mocking required for
this router because every write goes through normal SQLAlchemy sessions.
"""

from __future__ import annotations

import httpx
import pytest

from nexus_api import config as _cfg_mod

WORKER_TOKEN = "dev-bypass"  # Matches conftest `_test_settings` default.


def _worker_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {WORKER_TOKEN}",
        "X-CSRF-Token": "test-csrf-token-fixed",
    }


def _sample_request(
    outcome: str = "approved_clean",
    *,
    action_category: str = "email_send",
    agent_id: str = "agent-heraldo",
    org_id: str = "madfam",
    recipient_email: str = "alice@example.com",
) -> dict:
    return {
        "agent_id": agent_id,
        "action_category": action_category,
        "org_id": org_id,
        "context": {
            "template_id": "welcome",
            "recipient_email": recipient_email,
            "lead_stage": "new",
            "agent_role": "heraldo",
            "body_length": 400,
        },
        "outcome": outcome,
        "approver_id": "user-1",
        "latency_ms": 1200,
    }


@pytest.fixture(autouse=True)
def _ensure_worker_token() -> None:
    settings = _cfg_mod.get_settings()
    settings.worker_api_token = WORKER_TOKEN


# ============================================================================
# POST /api/v1/hitl/decisions
# ============================================================================


@pytest.mark.asyncio
class TestRecordDecision:
    async def test_requires_bearer(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/v1/hitl/decisions", json=_sample_request())
        assert resp.status_code == 401

    async def test_rejects_wrong_token(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request(),
            headers={
                "Authorization": "Bearer not-a-real-token",
                "X-CSRF-Token": "test-csrf-token-fixed",
            },
        )
        assert resp.status_code == 401

    async def test_records_first_decision(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean"),
            headers=_worker_headers(),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["bucket_key"]
        assert body["context_signature"]
        assert body["n_observed"] == 1
        # Beta(2,1) mean = 2/3.
        assert body["confidence"] == pytest.approx(2 / 3)
        # Sprint 1: tier always ASK.
        assert body["tier"] == "ask"

    async def test_same_context_aggregates_into_one_bucket(self, client: httpx.AsyncClient) -> None:
        for _ in range(3):
            await client.post(
                "/api/v1/hitl/decisions",
                json=_sample_request("approved_clean"),
                headers=_worker_headers(),
            )
        resp = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean"),
            headers=_worker_headers(),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["n_observed"] == 4
        # α after 4 clean = 1 + 4 = 5; β = 1; mean = 5/6.
        assert body["confidence"] == pytest.approx(5 / 6)

    async def test_different_context_creates_new_bucket(self, client: httpx.AsyncClient) -> None:
        r1 = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean", recipient_email="a@example.com"),
            headers=_worker_headers(),
        )
        r2 = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean", recipient_email="a@other.com"),
            headers=_worker_headers(),
        )
        assert r1.json()["bucket_key"] != r2.json()["bucket_key"]
        # Both are first-of-bucket, so both should read n_observed=1.
        assert r1.json()["n_observed"] == 1
        assert r2.json()["n_observed"] == 1

    async def test_mixed_outcomes_reflect_in_confidence(self, client: httpx.AsyncClient) -> None:
        # 4 approve + 1 reject — mean of Beta(5, 2) = 5/7 ≈ 0.714.
        for _ in range(4):
            await client.post(
                "/api/v1/hitl/decisions",
                json=_sample_request("approved_clean"),
                headers=_worker_headers(),
            )
        resp = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("rejected"),
            headers=_worker_headers(),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["n_observed"] == 5
        assert body["confidence"] == pytest.approx(5 / 7)

    async def test_downstream_revert_does_not_bump_observed(
        self, client: httpx.AsyncClient
    ) -> None:
        approve_resp = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean"),
            headers=_worker_headers(),
        )
        assert approve_resp.json()["n_observed"] == 1
        revert_resp = await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("downstream_reverted"),
            headers=_worker_headers(),
        )
        assert revert_resp.status_code == 201
        body = revert_resp.json()
        assert body["n_observed"] == 1  # unchanged — revert refers to prior approval


# ============================================================================
# GET /api/v1/hitl/confidence
# ============================================================================


@pytest.mark.asyncio
class TestConfidenceDashboard:
    async def test_dashboard_empty_when_no_decisions(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await client.get("/api/v1/hitl/confidence", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_buckets"] == 0
        assert body["total_decisions"] == 0
        assert body["buckets"] == []

    async def test_dashboard_lists_buckets_with_counts(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Seed two distinct buckets.
        for _ in range(3):
            await client.post(
                "/api/v1/hitl/decisions",
                json=_sample_request("approved_clean", recipient_email="alice@example.com"),
                headers=_worker_headers(),
            )
        await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("rejected", recipient_email="bob@other.com"),
            headers=_worker_headers(),
        )

        resp = await client.get("/api/v1/hitl/confidence", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_buckets"] == 2
        assert body["total_decisions"] == 4
        # Sorted by n_observed desc — the 3-approval bucket comes first.
        assert body["buckets"][0]["n_observed"] == 3
        assert body["buckets"][1]["n_observed"] == 1

    async def test_dashboard_filters_by_action_category(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean", action_category="email_send"),
            headers=_worker_headers(),
        )
        await client.post(
            "/api/v1/hitl/decisions",
            json={
                **_sample_request("approved_clean"),
                "action_category": "deploy",
                "context": {
                    "repo": "nexus",
                    "environment": "production",
                    "changed_paths": ["src/x.py"],
                },
            },
            headers=_worker_headers(),
        )
        resp = await client.get(
            "/api/v1/hitl/confidence?action_category=deploy",
            headers=auth_headers,
        )
        body = resp.json()
        assert len(body["buckets"]) == 1
        assert body["buckets"][0]["action_category"] == "deploy"

    async def test_dashboard_respects_min_observed(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # Three decisions in bucket A.
        for _ in range(3):
            await client.post(
                "/api/v1/hitl/decisions",
                json=_sample_request("approved_clean", recipient_email="a@a.com"),
                headers=_worker_headers(),
            )
        # One decision in bucket B.
        await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean", recipient_email="b@b.com"),
            headers=_worker_headers(),
        )
        resp = await client.get("/api/v1/hitl/confidence?min_observed=2", headers=auth_headers)
        body = resp.json()
        assert len(body["buckets"]) == 1
        assert body["buckets"][0]["n_observed"] == 3

    async def test_dashboard_requires_admin(self, client: httpx.AsyncClient) -> None:
        """No Authorization = 401; that's the admin gate firing."""
        resp = await client.get("/api/v1/hitl/confidence")
        assert resp.status_code in (401, 403)


# ============================================================================
# GET /api/v1/hitl/decisions
# ============================================================================


@pytest.mark.asyncio
class TestDecisionsList:
    async def test_lists_recent_decisions(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        for outcome in ("approved_clean", "rejected", "approved_modified"):
            await client.post(
                "/api/v1/hitl/decisions",
                json=_sample_request(outcome),
                headers=_worker_headers(),
            )
        resp = await client.get("/api/v1/hitl/decisions", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        # Newest first.
        assert body["decisions"][0]["outcome"] == "approved_modified"
        assert body["decisions"][-1]["outcome"] == "approved_clean"

    async def test_filters_by_outcome(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        for outcome in ("approved_clean", "approved_clean", "rejected"):
            await client.post(
                "/api/v1/hitl/decisions",
                json=_sample_request(outcome),
                headers=_worker_headers(),
            )
        resp = await client.get("/api/v1/hitl/decisions?outcome=rejected", headers=auth_headers)
        body = resp.json()
        assert len(body["decisions"]) == 1
        assert body["decisions"][0]["outcome"] == "rejected"

    async def test_filters_by_agent_id(
        self, client: httpx.AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean", agent_id="agent-a"),
            headers=_worker_headers(),
        )
        await client.post(
            "/api/v1/hitl/decisions",
            json=_sample_request("approved_clean", agent_id="agent-b"),
            headers=_worker_headers(),
        )
        resp = await client.get("/api/v1/hitl/decisions?agent_id=agent-a", headers=auth_headers)
        body = resp.json()
        assert len(body["decisions"]) == 1
        assert body["decisions"][0]["agent_id"] == "agent-a"
