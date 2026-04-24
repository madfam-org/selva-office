"""Tests for the cross-service unified audit aggregator (``/api/v1/audit/unified``).

Covers:
- Empty-result path
- Merging rows from all four Selva ledgers in timestamp-DESC order
- ``source`` filter restricts the query set
- ``actor`` filter narrows rows
- ``since`` / ``until`` bounds
- Cursor pagination drives strictly-older continuation
- Unknown source values are rejected with 400
- RBAC: non-admin users are forced to ``actor = own sub`` regardless
  of what they pass.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.auth import get_current_user
from nexus_api.main import app as _fastapi_app
from nexus_api.models import (
    ConfigmapAuditLog,
    GithubAdminAuditLog,
    SecretAuditLog,
    WebhookAuditLog,
)

# ---------------------------------------------------------------------------
# Fixture helpers — build minimal valid rows for each Selva ledger
# ---------------------------------------------------------------------------


def _fake_sig() -> str:
    """Return a dummy 64-char signature (we don't verify it here)."""
    return "0" * 64


def _secret_row(
    *,
    created_at: datetime,
    actor_user_sub: str | None = "user-alice",
    status: str = "applied",
) -> SecretAuditLog:
    return SecretAuditLog(
        id=uuid.uuid4(),
        created_at=created_at,
        agent_id=None,
        actor_user_sub=actor_user_sub,
        target_cluster="prod",
        target_namespace="karafiel",
        target_secret_name="karafiel-secrets",
        target_key="STRIPE_SECRET_KEY",
        operation="write",
        value_sha256_prefix="deadbeef",
        predecessor_sha256_prefix=None,
        source="selva.secrets.write_kubernetes_secret",
        rationale="test rotation",
        approval_request_id=uuid.uuid4(),
        approval_chain=[],
        status=status,
        error_message=None,
        rollback_of_id=None,
        signature_sha256=_fake_sig(),
    )


def _github_row(
    *,
    created_at: datetime,
    actor_user_sub: str | None = "user-bob",
    status: str = "applied",
) -> GithubAdminAuditLog:
    return GithubAdminAuditLog(
        id=uuid.uuid4(),
        created_at=created_at,
        agent_id=None,
        actor_user_sub=actor_user_sub,
        operation="set_branch_protection",
        target_org="madfam-org",
        target_repo="enclii",
        target_team_slug=None,
        target_branch="main",
        token_sha256_prefix="cafebabe",
        request_body={"required_reviews": 2},
        response_summary={"updated": True},
        rationale="enforce review gate",
        request_id="req-github-1",
        approval_request_id=uuid.uuid4(),
        approval_chain=[],
        status=status,
        error_message=None,
        rollback_of_id=None,
        signature_sha256=_fake_sig(),
    )


def _configmap_row(
    *,
    created_at: datetime,
    actor_user_sub: str | None = "user-carol",
    status: str = "applied",
) -> ConfigmapAuditLog:
    return ConfigmapAuditLog(
        id=uuid.uuid4(),
        created_at=created_at,
        agent_id=None,
        actor_user_sub=actor_user_sub,
        request_id="req-cm-1",
        target_cluster="prod",
        target_namespace="fortuna",
        target_configmap_name="fortuna-config",
        target_key="FEATURE_ZEITGEIST",
        operation="write",
        value_sha256_prefix="aaaa1111",
        previous_value_sha256_prefix="bbbb2222",
        rationale="flip flag",
        hitl_level="ask",
        approval_request_id=uuid.uuid4(),
        approval_chain=[],
        status=status,
        error_message=None,
        rollback_of_id=None,
        signature_sha256=_fake_sig(),
    )


def _webhook_row(
    *,
    created_at: datetime,
    actor_user_sub: str | None = "user-dan",
    status: str = "applied",
) -> WebhookAuditLog:
    return WebhookAuditLog(
        id=uuid.uuid4(),
        created_at=created_at,
        agent_id=None,
        actor_user_sub=actor_user_sub,
        provider="stripe",
        action="create",
        webhook_id="we_test_123",
        target_url_sha256_prefix="12345678",
        events_registered=["checkout.session.completed"],
        linked_secret_audit_id=None,
        resulting_secret_name="karafiel/karafiel-secrets:STRIPE_WEBHOOK_SECRET",
        approval_request_id=uuid.uuid4(),
        approval_chain=[],
        rationale="register stripe webhook",
        status=status,
        error_message=None,
        request_id="req-wh-1",
        signature_sha256=_fake_sig(),
    )


async def _seed_all(db: AsyncSession, base_ts: datetime) -> None:
    """Seed one row in each ledger, 10 minutes apart, oldest first."""
    db.add(_secret_row(created_at=base_ts))
    db.add(_github_row(created_at=base_ts + timedelta(minutes=10)))
    db.add(_configmap_row(created_at=base_ts + timedelta(minutes=20)))
    db.add(_webhook_row(created_at=base_ts + timedelta(minutes=30)))
    await db.commit()


# ---------------------------------------------------------------------------
# RBAC override helpers
# ---------------------------------------------------------------------------


def _override_user(roles: list[str], sub: str = "test-user") -> Any:
    async def _fake_user() -> dict[str, Any]:
        return {"sub": sub, "roles": roles, "org_id": "default", "email": None}

    return _fake_user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unified_empty(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    """With no rows seeded, the endpoint returns empty events and no cursor."""
    resp = await client.get("/api/v1/audit/unified/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"] == []
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_unified_merges_all_sources(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """All four ledgers should appear in timestamp-DESC order."""
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    await _seed_all(db_session, base)

    resp = await client.get("/api/v1/audit/unified/", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["events"]) == 4
    # Newest first: webhook (+30) > config (+20) > github (+10) > secret (+0)
    sources = [e["source"] for e in data["events"]]
    assert sources == [
        "selva_webhook",
        "selva_config",
        "selva_github",
        "selva_secret",
    ]
    # Category labels match.
    assert [e["category"] for e in data["events"]] == [
        "webhook",
        "config",
        "github",
        "secret",
    ]


@pytest.mark.asyncio
async def test_unified_source_filter(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """The ``source`` query param limits the query set."""
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    await _seed_all(db_session, base)

    resp = await client.get(
        "/api/v1/audit/unified/?source=selva_secret&source=selva_github",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert {e["source"] for e in data["events"]} == {"selva_secret", "selva_github"}
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_unified_rejects_unknown_source(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """A source name not in the four Selva ledgers returns 400."""
    resp = await client.get("/api/v1/audit/unified/?source=bogus", headers=auth_headers)
    assert resp.status_code == 400
    assert "Unknown source" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unified_since_until(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """``since`` / ``until`` are inclusive bounds on ``created_at``."""
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    await _seed_all(db_session, base)

    # Narrow to just the middle two rows (github at +10m, config at +20m).
    # NB: httpx does not auto-encode ``+`` in query strings, so pass params
    # via the ``params=`` kwarg and let it percent-encode them.
    resp = await client.get(
        "/api/v1/audit/unified/",
        params={
            "since": (base + timedelta(minutes=5)).isoformat(),
            "until": (base + timedelta(minutes=25)).isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    sources = {e["source"] for e in data["events"]}
    assert sources == {"selva_github", "selva_config"}


@pytest.mark.asyncio
async def test_unified_cursor_pagination(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Cursor drives strictly-older continuation, no duplicates across pages."""
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    await _seed_all(db_session, base)

    resp1 = await client.get("/api/v1/audit/unified/?limit=2", headers=auth_headers)
    assert resp1.status_code == 200
    page1 = resp1.json()
    assert len(page1["events"]) == 2
    assert page1["next_cursor"] is not None
    first_ids = {(e["source"], e["timestamp"]) for e in page1["events"]}

    resp2 = await client.get(
        f"/api/v1/audit/unified/?limit=2&cursor={page1['next_cursor']}",
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    page2 = resp2.json()
    assert len(page2["events"]) == 2
    second_ids = {(e["source"], e["timestamp"]) for e in page2["events"]}
    # No overlap between pages.
    assert not (first_ids & second_ids)
    # No more pages after the fourth row.
    assert page2["next_cursor"] is None


@pytest.mark.asyncio
async def test_unified_actor_filter(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """``actor`` filters the merged stream by ``actor_user_sub`` across ledgers."""
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    # Alice appears in secret + config; Bob only in github.
    db_session.add(_secret_row(created_at=base, actor_user_sub="user-alice"))
    db_session.add(_github_row(created_at=base + timedelta(minutes=5), actor_user_sub="user-bob"))
    db_session.add(
        _configmap_row(created_at=base + timedelta(minutes=10), actor_user_sub="user-alice")
    )
    await db_session.commit()

    resp = await client.get("/api/v1/audit/unified/?actor=user-alice", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    actors = {e["actor"] for e in data["events"]}
    assert actors == {"user-alice"}
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_unified_non_admin_is_forced_to_own_sub(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A non-admin caller can never see rows authored by a different sub.

    Dev-auth-bypass returns the ``admin`` role, so we override the
    ``get_current_user`` dependency here to simulate a plain user JWT.
    """
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    db_session.add(_secret_row(created_at=base, actor_user_sub="user-alice"))
    db_session.add(_github_row(created_at=base, actor_user_sub="user-bob"))
    await db_session.commit()

    _fastapi_app.dependency_overrides[get_current_user] = _override_user(
        roles=["viewer"], sub="user-alice"
    )
    try:
        # Even if Alice asks for Bob's rows, the server forces actor=alice.
        resp = await client.get(
            "/api/v1/audit/unified/?actor=user-bob",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        actors = {e["actor"] for e in data["events"]}
        assert actors == {"user-alice"}
    finally:
        _fastapi_app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_unified_admin_sees_all_actors(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Admin callers can query across actors without restriction."""
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    db_session.add(_secret_row(created_at=base, actor_user_sub="user-alice"))
    db_session.add(_github_row(created_at=base, actor_user_sub="user-bob"))
    await db_session.commit()

    _fastapi_app.dependency_overrides[get_current_user] = _override_user(
        roles=["admin"], sub="admin-root"
    )
    try:
        resp = await client.get(
            "/api/v1/audit/unified/",
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        actors = {e["actor"] for e in data["events"]}
        assert actors == {"user-alice", "user-bob"}
    finally:
        _fastapi_app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_unified_outcome_maps_status(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Status strings collapse to the canonical outcome triad."""
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    db_session.add(_secret_row(created_at=base, status="applied"))
    db_session.add(_github_row(created_at=base + timedelta(minutes=1), status="denied"))
    db_session.add(_configmap_row(created_at=base + timedelta(minutes=2), status="failed"))
    await db_session.commit()

    resp = await client.get("/api/v1/audit/unified/", headers=auth_headers)
    assert resp.status_code == 200
    outcomes = {e["category"]: e["outcome"] for e in resp.json()["events"]}
    assert outcomes["secret"] == "success"
    assert outcomes["github"] == "denied"
    assert outcomes["config"] == "failure"


@pytest.mark.asyncio
async def test_unified_rejects_bad_cursor(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Malformed cursor strings return 400, not 500."""
    resp = await client.get("/api/v1/audit/unified/?cursor=not-a-date", headers=auth_headers)
    assert resp.status_code == 400
