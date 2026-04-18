"""Tests for Google and Microsoft calendar adapters using mock httpx transports."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from selva_calendar import CalendarEvent, CalendarProvider
from selva_calendar.google import GoogleCalendarAdapter
from selva_calendar.microsoft import MicrosoftCalendarAdapter

# ---------------------------------------------------------------------------
# Mock transport helpers
# ---------------------------------------------------------------------------


class MockTransport(httpx.AsyncBaseTransport):
    """Return a fixed JSON response for any request."""

    def __init__(self, json_body: dict | list, *, status_code: int = 200) -> None:
        self._json_body = json_body
        self._status_code = status_code
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        import json

        return httpx.Response(
            status_code=self._status_code,
            content=json.dumps(self._json_body).encode(),
            headers={"Content-Type": "application/json"},
        )


# ---------------------------------------------------------------------------
# Google adapter tests
# ---------------------------------------------------------------------------


class TestGoogleCalendarAdapter:
    """Tests for GoogleCalendarAdapter against a mock transport."""

    @pytest.mark.asyncio()
    async def test_list_events_returns_calendar_events(self) -> None:
        """list_events parses Google Calendar API response into CalendarEvent list."""
        now = datetime(2026, 3, 14, 10, 0, 0, tzinfo=UTC)
        later = now + timedelta(hours=1)

        google_response = {
            "items": [
                {
                    "id": "evt-001",
                    "summary": "Team Standup",
                    "start": {"dateTime": now.isoformat()},
                    "end": {"dateTime": later.isoformat()},
                    "hangoutLink": "https://meet.google.com/abc",
                    "organizer": {"email": "boss@example.com"},
                    "attendees": [
                        {"email": "alice@example.com"},
                        {"email": "bob@example.com"},
                    ],
                },
            ]
        }

        transport = MockTransport(google_response)
        adapter = GoogleCalendarAdapter.__new__(GoogleCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://www.googleapis.com/calendar/v3",
            transport=transport,
        )

        events = await adapter.list_events(now, later)

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CalendarEvent)
        assert evt.id == "evt-001"
        assert evt.title == "Team Standup"
        assert evt.meeting_url == "https://meet.google.com/abc"
        assert evt.organizer == "boss@example.com"
        assert evt.attendees == ["alice@example.com", "bob@example.com"]
        assert evt.provider == CalendarProvider.GOOGLE
        assert not evt.is_all_day

        await adapter.close()

    @pytest.mark.asyncio()
    async def test_list_events_all_day(self) -> None:
        """list_events correctly marks all-day events."""
        google_response = {
            "items": [
                {
                    "id": "evt-allday",
                    "summary": "Company Holiday",
                    "start": {"date": "2026-03-14"},
                    "end": {"date": "2026-03-15"},
                },
            ]
        }

        transport = MockTransport(google_response)
        adapter = GoogleCalendarAdapter.__new__(GoogleCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://www.googleapis.com/calendar/v3",
            transport=transport,
        )

        events = await adapter.list_events(
            datetime(2026, 3, 14, tzinfo=UTC),
            datetime(2026, 3, 15, tzinfo=UTC),
        )

        assert len(events) == 1
        assert events[0].is_all_day is True
        assert events[0].title == "Company Holiday"

        await adapter.close()

    @pytest.mark.asyncio()
    async def test_list_events_empty(self) -> None:
        """list_events returns empty list when no events."""
        transport = MockTransport({"items": []})
        adapter = GoogleCalendarAdapter.__new__(GoogleCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://www.googleapis.com/calendar/v3",
            transport=transport,
        )

        events = await adapter.list_events(
            datetime(2026, 3, 14, tzinfo=UTC),
            datetime(2026, 3, 15, tzinfo=UTC),
        )
        assert events == []
        await adapter.close()

    @pytest.mark.asyncio()
    async def test_check_busy_returns_true(self) -> None:
        """check_busy returns True when there is an active event."""
        now = datetime(2026, 3, 14, 10, 0, 0, tzinfo=UTC)
        google_response = {
            "items": [
                {
                    "id": "evt-busy",
                    "summary": "Meeting",
                    "start": {"dateTime": now.isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                },
            ]
        }

        transport = MockTransport(google_response)
        adapter = GoogleCalendarAdapter.__new__(GoogleCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://www.googleapis.com/calendar/v3",
            transport=transport,
        )

        assert await adapter.check_busy(now) is True
        await adapter.close()

    @pytest.mark.asyncio()
    async def test_check_busy_returns_false(self) -> None:
        """check_busy returns False when no events are active."""
        transport = MockTransport({"items": []})
        adapter = GoogleCalendarAdapter.__new__(GoogleCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://www.googleapis.com/calendar/v3",
            transport=transport,
        )

        assert await adapter.check_busy(datetime(2026, 3, 14, 10, 0, 0, tzinfo=UTC)) is False
        await adapter.close()


# ---------------------------------------------------------------------------
# Microsoft adapter tests
# ---------------------------------------------------------------------------


class TestMicrosoftCalendarAdapter:
    """Tests for MicrosoftCalendarAdapter against a mock transport."""

    @pytest.mark.asyncio()
    async def test_list_events_returns_calendar_events(self) -> None:
        """list_events parses Microsoft Graph API response into CalendarEvent list."""
        ms_response = {
            "value": [
                {
                    "id": "ms-evt-001",
                    "subject": "Sprint Planning",
                    "start": {"dateTime": "2026-03-14T09:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-03-14T10:00:00.0000000", "timeZone": "UTC"},
                    "isAllDay": False,
                    "onlineMeetingUrl": "https://teams.microsoft.com/xyz",
                    "organizer": {
                        "emailAddress": {"address": "manager@example.com"}
                    },
                    "attendees": [
                        {"emailAddress": {"address": "dev1@example.com"}},
                        {"emailAddress": {"address": "dev2@example.com"}},
                    ],
                },
            ]
        }

        transport = MockTransport(ms_response)
        adapter = MicrosoftCalendarAdapter.__new__(MicrosoftCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://graph.microsoft.com/v1.0",
            transport=transport,
        )

        events = await adapter.list_events(
            datetime(2026, 3, 14, 8, 0, 0, tzinfo=UTC),
            datetime(2026, 3, 14, 12, 0, 0, tzinfo=UTC),
        )

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CalendarEvent)
        assert evt.id == "ms-evt-001"
        assert evt.title == "Sprint Planning"
        assert evt.meeting_url == "https://teams.microsoft.com/xyz"
        assert evt.organizer == "manager@example.com"
        assert evt.attendees == ["dev1@example.com", "dev2@example.com"]
        assert evt.provider == CalendarProvider.MICROSOFT
        assert not evt.is_all_day

        await adapter.close()

    @pytest.mark.asyncio()
    async def test_list_events_empty(self) -> None:
        """list_events returns empty list when Graph API returns no events."""
        transport = MockTransport({"value": []})
        adapter = MicrosoftCalendarAdapter.__new__(MicrosoftCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://graph.microsoft.com/v1.0",
            transport=transport,
        )

        events = await adapter.list_events(
            datetime(2026, 3, 14, tzinfo=UTC),
            datetime(2026, 3, 15, tzinfo=UTC),
        )
        assert events == []
        await adapter.close()

    @pytest.mark.asyncio()
    async def test_check_busy_returns_true(self) -> None:
        """check_busy returns True when there is an active event."""
        ms_response = {
            "value": [
                {
                    "id": "ms-busy",
                    "subject": "Call",
                    "start": {"dateTime": "2026-03-14T10:00:00", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-03-14T11:00:00", "timeZone": "UTC"},
                    "isAllDay": False,
                },
            ]
        }

        transport = MockTransport(ms_response)
        adapter = MicrosoftCalendarAdapter.__new__(MicrosoftCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://graph.microsoft.com/v1.0",
            transport=transport,
        )

        assert await adapter.check_busy(datetime(2026, 3, 14, 10, 30, 0, tzinfo=UTC)) is True
        await adapter.close()

    @pytest.mark.asyncio()
    async def test_check_busy_returns_false(self) -> None:
        """check_busy returns False when no events are active."""
        transport = MockTransport({"value": []})
        adapter = MicrosoftCalendarAdapter.__new__(MicrosoftCalendarAdapter)
        adapter._token = "test-token"
        adapter._client = httpx.AsyncClient(
            base_url="https://graph.microsoft.com/v1.0",
            transport=transport,
        )

        assert await adapter.check_busy(datetime(2026, 3, 14, 10, 0, 0, tzinfo=UTC)) is False
        await adapter.close()
