"""Tests for the Calendar Integration REST API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.models import CalendarConnection


async def _create_connection(
    db: AsyncSession,
    *,
    user_id: str = "dev-user-00000000",
    provider: str = "google",
    access_token: str = "test-access-token",
    refresh_token: str | None = "test-refresh-token",
    org_id: str = "dev-org",
) -> CalendarConnection:
    """Insert a calendar connection directly into the database."""
    conn = CalendarConnection(
        user_id=user_id,
        provider=provider,
        access_token=access_token,
        refresh_token=refresh_token,
        org_id=org_id,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return conn


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_calendar_status_not_connected(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Status returns connected=False when no calendar is linked."""
    resp = await client.get("/api/v1/calendar/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["provider"] is None


@pytest.mark.asyncio()
async def test_calendar_status_connected(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Status returns connected=True with provider details when linked."""
    await _create_connection(db_session, provider="google")
    await db_session.commit()

    resp = await client.get("/api/v1/calendar/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["provider"] == "google"
    assert data["connected_at"] is not None


# ---------------------------------------------------------------------------
# POST /connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_connect_calendar_new(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Connecting a calendar for the first time creates a new connection."""
    payload = {
        "provider": "google",
        "access_token": "ya29.test-access",
        "refresh_token": "1//test-refresh",
    }
    resp = await client.post("/api/v1/calendar/connect", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["connected"] is True
    assert data["provider"] == "google"


@pytest.mark.asyncio()
async def test_connect_calendar_update_existing(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Connecting again updates the existing connection tokens."""
    await _create_connection(db_session, provider="google", access_token="old-token")
    await db_session.commit()

    payload = {
        "provider": "microsoft",
        "access_token": "new-ms-token",
    }
    resp = await client.post("/api/v1/calendar/connect", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "microsoft"

    # Verify status reflects the update
    status_resp = await client.get("/api/v1/calendar/status", headers=auth_headers)
    assert status_resp.json()["provider"] == "microsoft"


@pytest.mark.asyncio()
async def test_connect_calendar_missing_token(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Connecting without an access_token returns 422."""
    payload = {"provider": "google", "access_token": ""}
    resp = await client.post("/api/v1/calendar/connect", json=payload, headers=auth_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_disconnect_calendar(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Disconnecting removes the calendar connection."""
    await _create_connection(db_session)
    await db_session.commit()

    resp = await client.delete("/api/v1/calendar/disconnect", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["disconnected"] is True

    # Verify disconnected
    status_resp = await client.get("/api/v1/calendar/status", headers=auth_headers)
    assert status_resp.json()["connected"] is False


@pytest.mark.asyncio()
async def test_disconnect_calendar_not_found(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Disconnecting without a connection returns 404."""
    resp = await client.delete("/api/v1/calendar/disconnect", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_list_events_no_connection(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Listing events with no connection returns empty list and not busy."""
    resp = await client.get("/api/v1/calendar/events", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"] == []
    assert data["is_busy"] is False


@pytest.mark.asyncio()
async def test_list_events_with_connection(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Listing events with a connection fetches from the calendar adapter."""
    await _create_connection(db_session, provider="google")
    await db_session.commit()

    now = datetime.now(UTC)

    with patch(
        "nexus_api.routers.calendar._fetch_events",
        new_callable=AsyncMock,
    ) as mock_fetch:
        from selva_calendar import CalendarEvent, CalendarProvider

        mock_fetch.return_value = [
            CalendarEvent(
                id="evt-1",
                title="Team Standup",
                start=now,
                end=now,
                is_all_day=False,
                meeting_url="https://meet.google.com/abc",
                organizer="boss@example.com",
                attendees=["alice@example.com"],
                provider=CalendarProvider.GOOGLE,
            )
        ]

        resp = await client.get("/api/v1/calendar/events", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["title"] == "Team Standup"
        assert data["events"][0]["provider"] == "google"


@pytest.mark.asyncio()
async def test_list_events_adapter_failure_returns_empty(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """When the calendar adapter fails, return empty list gracefully."""
    await _create_connection(db_session, provider="google")
    await db_session.commit()

    with patch(
        "nexus_api.routers.calendar._fetch_events",
        new_callable=AsyncMock,
        side_effect=Exception("API timeout"),
    ):
        resp = await client.get("/api/v1/calendar/events", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["is_busy"] is False


# ---------------------------------------------------------------------------
# Auth requirement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_calendar_requires_auth(client: httpx.AsyncClient) -> None:
    """Calendar endpoints require authentication."""
    resp = await client.get("/api/v1/calendar/status")
    assert resp.status_code in (401, 403)
