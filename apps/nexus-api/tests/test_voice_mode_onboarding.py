"""Tests for voice-mode onboarding + consent ledger (migration 0018).

Verifies:
- The status endpoint reflects NULL voice_mode as "onboarding incomplete".
- POST /onboarding/voice-mode requires typed confirmation matching the clause.
- user_direct mode rejects a mismatched phrase.
- A successful selection writes a ledger row and sets tenant.voice_mode.
- Second POST returns 409 (must use PUT to change).
- PUT /settings/outbound-voice appends a *new* ledger row (append-only).
- voice_mode.selected/changed events land in task_events.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.models import ConsentLedger, TaskEvent, TenantConfig
from nexus_api.routers.onboarding import (
    CLAUSE_VERSION,
    CONSENT_CLAUSES,
    compute_signature,
    verify_signature,
)

_TENANTS_URL = "/api/v1/tenants"


async def _bootstrap_tenant(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    resp = await client.post(
        f"{_TENANTS_URL}/",
        headers=headers,
        json={"org_name": "Voice Test Co"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_status_reports_onboarding_incomplete_before_selection(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    resp = await client.get("/api/v1/onboarding/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["voice_mode"] is None
    assert body["onboarding_complete"] is False
    assert body["clause_version"] == CLAUSE_VERSION


@pytest.mark.asyncio
async def test_preview_returns_clause_for_each_mode(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    for mode in ("user_direct", "dyad_selva_plus_user", "agent_identified"):
        resp = await client.get(
            f"/api/v1/onboarding/voice-mode/preview/{mode}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == mode
        assert body["clause_version"] == CLAUSE_VERSION
        assert body["typed_phrase"]
        assert body["heads_up"]


@pytest.mark.asyncio
async def test_select_voice_mode_rejects_mismatched_phrase(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    resp = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "user_direct", "typed_confirmation": "nope"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_select_voice_mode_writes_ledger_and_sets_tenant(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    phrase = CONSENT_CLAUSES["dyad_selva_plus_user"]["typed_phrase"]
    resp = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "dyad_selva_plus_user", "typed_confirmation": phrase},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["voice_mode"] == "dyad_selva_plus_user"
    assert body["onboarding_complete"] is True

    # Tenant row updated
    tenant = (await db_session.execute(select(TenantConfig))).scalar_one()
    assert tenant.voice_mode == "dyad_selva_plus_user"

    # Ledger row created
    ledgers = (await db_session.execute(select(ConsentLedger))).scalars().all()
    assert len(ledgers) == 1
    row = ledgers[0]
    assert row.mode == "dyad_selva_plus_user"
    assert row.clause_version == CLAUSE_VERSION
    assert row.typed_confirmation == phrase
    assert len(row.signature_sha256) == 64
    assert row.user_email  # must come from JWT


@pytest.mark.asyncio
async def test_second_select_returns_409(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    phrase = CONSENT_CLAUSES["dyad_selva_plus_user"]["typed_phrase"]
    resp = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "dyad_selva_plus_user", "typed_confirmation": phrase},
    )
    assert resp.status_code == 201

    resp2 = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "agent_identified", "typed_confirmation": phrase},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_change_voice_mode_appends_new_ledger_row(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    # First selection
    first = CONSENT_CLAUSES["dyad_selva_plus_user"]["typed_phrase"]
    await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "dyad_selva_plus_user", "typed_confirmation": first},
    )
    # Change via PUT
    second = CONSENT_CLAUSES["agent_identified"]["typed_phrase"]
    resp = await client.put(
        "/api/v1/settings/outbound-voice",
        headers=auth_headers,
        json={"mode": "agent_identified", "typed_confirmation": second},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["voice_mode"] == "agent_identified"

    # Both rows present — ledger is append-only
    ledgers = (await db_session.execute(select(ConsentLedger))).scalars().all()
    modes = sorted(r.mode for r in ledgers)
    assert modes == ["agent_identified", "dyad_selva_plus_user"]


@pytest.mark.asyncio
async def test_voice_mode_selected_emits_event(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    phrase = CONSENT_CLAUSES["user_direct"]["typed_phrase"]
    resp = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "user_direct", "typed_confirmation": phrase},
    )
    assert resp.status_code == 201

    events = (
        (
            await db_session.execute(
                select(TaskEvent).where(TaskEvent.event_type == "voice_mode.selected")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload or {}
    assert payload.get("mode") == "user_direct"
    assert payload.get("clause_version") == CLAUSE_VERSION


@pytest.mark.asyncio
async def test_preview_rejects_unknown_mode(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get(
        "/api/v1/onboarding/voice-mode/preview/bogus-mode", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_select_rejects_unknown_mode(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    resp = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "not-a-real-mode", "typed_confirmation": "anything"},
    )
    # pydantic validation returns 422 for unknown mode values
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_select_fails_without_tenant_config(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # No tenant created -- voice-mode selection must 404.
    phrase = CONSENT_CLAUSES["dyad_selva_plus_user"]["typed_phrase"]
    resp = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "dyad_selva_plus_user", "typed_confirmation": phrase},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tenant_response_exposes_voice_mode_after_selection(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    phrase = CONSENT_CLAUSES["dyad_selva_plus_user"]["typed_phrase"]
    await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "dyad_selva_plus_user", "typed_confirmation": phrase},
    )
    resp = await client.get("/api/v1/tenants/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["voice_mode"] == "dyad_selva_plus_user"


@pytest.mark.asyncio
async def test_verify_signature_detects_tampering(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _bootstrap_tenant(client, auth_headers)
    phrase = CONSENT_CLAUSES["agent_identified"]["typed_phrase"]
    resp = await client.post(
        "/api/v1/onboarding/voice-mode",
        headers=auth_headers,
        json={"mode": "agent_identified", "typed_confirmation": phrase},
    )
    assert resp.status_code == 201

    entry = (await db_session.execute(select(ConsentLedger))).scalar_one()

    # Fresh row — signature verifies.
    assert verify_signature(entry) is True

    # Mutate `mode` in-memory and verify the digest no longer matches.
    entry.mode = "user_direct"
    assert verify_signature(entry) is False


def test_compute_signature_is_deterministic() -> None:
    from datetime import UTC, datetime

    ts = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    args = dict(
        org_id="org-x",
        user_sub="sub-x",
        mode="user_direct",
        clause_version=CLAUSE_VERSION,
        typed_confirmation=CONSENT_CLAUSES["user_direct"]["typed_phrase"],
        created_at=ts,
    )
    assert compute_signature(**args) == compute_signature(**args)
    # Different field -> different digest.
    assert compute_signature(**{**args, "mode": "agent_identified"}) != compute_signature(**args)
