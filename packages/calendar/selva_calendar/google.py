"""Google Calendar adapter using the Calendar API v3."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from .types import CalendarEvent, CalendarProvider

logger = logging.getLogger(__name__)

_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarAdapter:
    """Fetch events and busy status from Google Calendar.

    Requires an OAuth2 access token with ``calendar.readonly`` scope.
    """

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=_CALENDAR_API_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
        *,
        calendar_id: str = "primary",
        max_results: int = 50,
    ) -> list[CalendarEvent]:
        """Return calendar events in the given time range.

        Uses ``GET /calendars/{calendarId}/events`` with ``timeMin``/``timeMax``
        parameters to fetch a single-page result set.
        """
        params: dict[str, str | int] = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": max_results,
        }
        resp = await self._client.get(
            f"/calendars/{calendar_id}/events",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        events: list[CalendarEvent] = []
        for item in data.get("items", []):
            start_raw = item.get("start", {})
            end_raw = item.get("end", {})
            is_all_day = "date" in start_raw and "dateTime" not in start_raw

            start_str = start_raw.get("dateTime") or start_raw.get("date", "")
            end_str = end_raw.get("dateTime") or end_raw.get("date", "")

            events.append(
                CalendarEvent(
                    id=item.get("id", ""),
                    title=item.get("summary", "(No title)"),
                    start=datetime.fromisoformat(start_str),
                    end=datetime.fromisoformat(end_str),
                    is_all_day=is_all_day,
                    meeting_url=item.get("hangoutLink"),
                    organizer=item.get("organizer", {}).get("email", ""),
                    attendees=[
                        a.get("email", "")
                        for a in item.get("attendees", [])
                        if a.get("email")
                    ],
                    provider=CalendarProvider.GOOGLE,
                )
            )
        return events

    async def check_busy(self, time: datetime | None = None) -> bool:
        """Return ``True`` if any event is currently active at the given time.

        Defaults to "now" when *time* is not supplied.
        """
        now = time or datetime.now(UTC)
        events = await self.list_events(now, now, max_results=1)
        return len(events) > 0
