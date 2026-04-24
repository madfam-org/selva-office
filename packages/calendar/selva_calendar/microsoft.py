"""Microsoft Calendar adapter using the Microsoft Graph API v1.0."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from .types import CalendarEvent, CalendarProvider

logger = logging.getLogger(__name__)

_GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


class MicrosoftCalendarAdapter:
    """Fetch events and busy status from Microsoft 365 / Outlook Calendar.

    Requires an OAuth2 access token with ``Calendars.Read`` scope.
    """

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=_GRAPH_API_BASE,
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
        max_results: int = 50,
    ) -> list[CalendarEvent]:
        """Return calendar events in the given time range.

        Uses ``GET /me/calendarview`` with ``startDateTime``/``endDateTime``
        query parameters.
        """
        params: dict[str, str | int] = {
            "startDateTime": time_min.isoformat(),
            "endDateTime": time_max.isoformat(),
            "$top": max_results,
            "$orderby": "start/dateTime",
            "$select": "id,subject,start,end,isAllDay,onlineMeetingUrl,organizer,attendees",
        }
        resp = await self._client.get("/me/calendarview", params=params)
        resp.raise_for_status()
        data = resp.json()

        events: list[CalendarEvent] = []
        for item in data.get("value", []):
            start_raw = item.get("start", {})
            end_raw = item.get("end", {})

            start_str = start_raw.get("dateTime", "")
            end_str = end_raw.get("dateTime", "")

            # Microsoft Graph returns an explicit timezone; fallback to UTC.
            start_tz = start_raw.get("timeZone", "UTC")
            end_tz = end_raw.get("timeZone", "UTC")

            start_dt = self._parse_graph_datetime(start_str, start_tz)
            end_dt = self._parse_graph_datetime(end_str, end_tz)

            meeting_url = item.get("onlineMeetingUrl") or None
            organizer_email = item.get("organizer", {}).get("emailAddress", {}).get("address", "")
            attendees = [
                a.get("emailAddress", {}).get("address", "")
                for a in item.get("attendees", [])
                if a.get("emailAddress", {}).get("address")
            ]

            events.append(
                CalendarEvent(
                    id=item.get("id", ""),
                    title=item.get("subject", "(No title)"),
                    start=start_dt,
                    end=end_dt,
                    is_all_day=item.get("isAllDay", False),
                    meeting_url=meeting_url,
                    organizer=organizer_email,
                    attendees=attendees,
                    provider=CalendarProvider.MICROSOFT,
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

    @staticmethod
    def _parse_graph_datetime(dt_str: str, tz_name: str) -> datetime:
        """Parse a Microsoft Graph datetime string.

        Graph returns ``2026-03-14T10:00:00.0000000`` with a separate
        ``timeZone`` field.  We normalise to a timezone-aware datetime
        using UTC when the zone is ``"UTC"`` or unrecognised.
        """
        # Strip fractional seconds beyond microseconds if present.
        if "." in dt_str:
            base, frac = dt_str.split(".", 1)
            frac = frac[:6]
            dt_str = f"{base}.{frac}"

        dt = datetime.fromisoformat(dt_str)

        # If the parsed datetime is naive, treat it as UTC.
        if dt.tzinfo is None and tz_name == "UTC":
            dt = dt.replace(tzinfo=UTC)

        return dt
