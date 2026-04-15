"""Calendar tools: create and list events via calendar adapters."""

from __future__ import annotations

import logging
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger("autoswarm.calendar_tools")


class CreateCalendarEventTool(BaseTool):
    name = "create_calendar_event"
    description = (
        "Create a calendar event with title, start/end times, description, and attendees. "
        "Uses the autoswarm_calendar Google adapter when available."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO 8601 format (e.g. 2026-04-15T09:00:00Z)",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO 8601 format",
                },
                "description": {
                    "type": "string",
                    "description": "Event description",
                    "default": "",
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses",
                    "default": [],
                },
                "calendar_id": {
                    "type": "string",
                    "description": "Calendar ID (defaults to primary)",
                    "default": "primary",
                },
            },
            "required": ["title", "start_time", "end_time"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        title = kwargs.get("title", "")
        start_time = kwargs.get("start_time", "")
        end_time = kwargs.get("end_time", "")
        description = kwargs.get("description", "")
        attendees = kwargs.get("attendees", [])
        calendar_id = kwargs.get("calendar_id", "primary")

        try:
            from autoswarm_calendar.google import GoogleCalendarAdapter

            adapter = GoogleCalendarAdapter()
            event = await adapter.create_event(
                calendar_id=calendar_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                attendees=attendees,
            )
            event_id = event.get("id", "unknown") if isinstance(event, dict) else "created"
            return ToolResult(
                output=f"Event '{title}' created (id={event_id})",
                data={
                    "event_id": event_id,
                    "title": title,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            )
        except ImportError:
            logger.warning("autoswarm_calendar not available")
            return ToolResult(
                success=False,
                error="Calendar not configured. Install autoswarm_calendar package.",
            )
        except Exception as exc:
            logger.error("create_calendar_event failed: %s", exc)
            return ToolResult(success=False, error=str(exc))


class ListCalendarEventsTool(BaseTool):
    name = "list_calendar_events"
    description = (
        "List calendar events for a given date. "
        "Uses the autoswarm_calendar Google adapter when available."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
                "calendar_id": {
                    "type": "string",
                    "description": "Calendar ID (defaults to primary)",
                    "default": "primary",
                },
            },
            "required": ["date"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        date = kwargs.get("date", "")
        calendar_id = kwargs.get("calendar_id", "primary")

        try:
            from autoswarm_calendar.google import GoogleCalendarAdapter

            adapter = GoogleCalendarAdapter()
            events = await adapter.list_events(
                calendar_id=calendar_id,
                time_min=f"{date}T00:00:00Z",
                time_max=f"{date}T23:59:59Z",
            )
            event_list = events if isinstance(events, list) else []
            summary = "\n".join(
                f"- {e.get('summary', 'Untitled')} ({e.get('start', {}).get('dateTime', '')})"
                for e in event_list
            )
            return ToolResult(
                output=summary or f"No events on {date}",
                data={"date": date, "events": event_list, "count": len(event_list)},
            )
        except ImportError:
            logger.warning("autoswarm_calendar not available")
            return ToolResult(
                success=False,
                error="Calendar not configured. Install autoswarm_calendar package.",
            )
        except Exception as exc:
            logger.error("list_calendar_events failed: %s", exc)
            return ToolResult(success=False, error=str(exc))
