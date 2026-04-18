"""Shared types for calendar integration adapters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class CalendarProvider(StrEnum):
    """Supported calendar providers."""

    GOOGLE = "google"
    MICROSOFT = "microsoft"


class CalendarEvent(BaseModel):
    """A calendar event normalised across providers."""

    id: str
    title: str
    start: datetime
    end: datetime
    is_all_day: bool = False
    meeting_url: str | None = None
    organizer: str = ""
    attendees: list[str] = []
    provider: CalendarProvider
