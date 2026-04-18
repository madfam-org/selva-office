"""Sentry issue + event management.

Sentry is the canonical error-tracking store across the MADFAM ecosystem
(12 services instrumented per the ecosystem-remediation-v2 memory). For
incident triage the swarm needs to: list recent issues, fetch an issue's
full context, mark issues resolved once the fix ships, list recent events
for an issue, and pull breadcrumbs (the Seer-style pre-error trail) for
root-cause analysis.

Auth uses a Sentry organization auth token (internal integration token) via
the ``SENTRY_API_TOKEN`` env var. Org slug via ``SENTRY_ORG_SLUG``. Base URL
defaults to ``https://sentry.io/api/0`` — override via ``SENTRY_API_BASE``
for self-hosted deployments.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

SENTRY_API_BASE = os.environ.get("SENTRY_API_BASE", "https://sentry.io/api/0")
SENTRY_API_TOKEN = os.environ.get("SENTRY_API_TOKEN", "")
SENTRY_ORG_SLUG = os.environ.get("SENTRY_ORG_SLUG", "")


def _creds_check() -> str | None:
    if not SENTRY_API_TOKEN:
        return "SENTRY_API_TOKEN must be set."
    if not SENTRY_ORG_SLUG:
        return "SENTRY_ORG_SLUG must be set."
    return None


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SENTRY_API_TOKEN}",
        "Content-Type": "application/json",
    }


async def _request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    url = f"{SENTRY_API_BASE.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method, url, headers=_headers(), params=params, json=json_body
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("detail") or body.get("message") or str(body)
    return f"HTTP {status}: {body}"


class SentryIssueListTool(BaseTool):
    """List Sentry issues for a project."""

    name = "sentry_issue_list"
    description = (
        "List Sentry issues for a project (``/projects/{org}/{project}/issues/``). "
        "Filter by 'status' (resolved/unresolved/ignored), an arbitrary "
        "'query' string (Sentry search DSL, e.g. 'is:unresolved level:error'), "
        "and 'limit' (default 25). Returns id, shortId, title, culprit, "
        "status, level, count, last_seen."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["resolved", "unresolved", "ignored"],
                },
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 25, "minimum": 1, "maximum": 100},
            },
            "required": ["project_slug"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        project_slug = kwargs["project_slug"]
        params: dict[str, Any] = {"limit": kwargs.get("limit", 25)}
        query_parts: list[str] = []
        if kwargs.get("status"):
            query_parts.append(f"is:{kwargs['status']}")
        if kwargs.get("query"):
            query_parts.append(kwargs["query"])
        if query_parts:
            params["query"] = " ".join(query_parts)
        try:
            status, body = await _request(
                "GET",
                f"/projects/{SENTRY_ORG_SLUG}/{project_slug}/issues/",
                params=params,
            )
            if status != 200 or not isinstance(body, list):
                return ToolResult(success=False, error=_err(status, body))
            issues = [
                {
                    "id": i.get("id"),
                    "shortId": i.get("shortId"),
                    "title": i.get("title"),
                    "culprit": i.get("culprit"),
                    "status": i.get("status"),
                    "level": i.get("level"),
                    "count": i.get("count"),
                    "userCount": i.get("userCount"),
                    "firstSeen": i.get("firstSeen"),
                    "lastSeen": i.get("lastSeen"),
                    "permalink": i.get("permalink"),
                }
                for i in body
            ]
            return ToolResult(
                success=True,
                output=f"Found {len(issues)} issue(s) in {project_slug}.",
                data={"issues": issues},
            )
        except Exception as e:
            logger.error("sentry_issue_list failed: %s", e)
            return ToolResult(success=False, error=str(e))


class SentryIssueGetTool(BaseTool):
    """Fetch one Sentry issue with full metadata."""

    name = "sentry_issue_get"
    description = (
        "Get a single Sentry issue by id (``/issues/{id}/``). Returns full "
        "metadata incl. tags, platform, assignee, stats, most-recent-event "
        "reference. Use before proposing a fix to ground the diagnosis in "
        "Sentry's actual data."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
            },
            "required": ["issue_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        issue_id = kwargs["issue_id"]
        try:
            status, body = await _request("GET", f"/issues/{issue_id}/")
            if status != 200 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"{body.get('shortId') or issue_id}: "
                    f"{body.get('title', '(no title)')}"
                ),
                data={
                    "id": body.get("id"),
                    "shortId": body.get("shortId"),
                    "title": body.get("title"),
                    "culprit": body.get("culprit"),
                    "status": body.get("status"),
                    "level": body.get("level"),
                    "platform": body.get("platform"),
                    "assignedTo": body.get("assignedTo"),
                    "count": body.get("count"),
                    "userCount": body.get("userCount"),
                    "firstSeen": body.get("firstSeen"),
                    "lastSeen": body.get("lastSeen"),
                    "permalink": body.get("permalink"),
                    "tags": body.get("tags") or [],
                    "stats": body.get("stats") or {},
                    "metadata": body.get("metadata") or {},
                },
            )
        except Exception as e:
            logger.error("sentry_issue_get failed: %s", e)
            return ToolResult(success=False, error=str(e))


class SentryIssueUpdateTool(BaseTool):
    """Update a Sentry issue (resolve, assign, change status)."""

    name = "sentry_issue_update"
    description = (
        "Update one Sentry issue via PUT ``/issues/{id}/``. 'status' accepts "
        "'resolved' / 'unresolved' / 'ignored'. 'assignedTo' is a Sentry "
        "username or team slug (prefix teams with '#'). Use to close out "
        "the issue once the fix PR ships and you've verified via "
        "sentry_event_list_for_issue that no fresh events have arrived."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["resolved", "unresolved", "ignored"],
                },
                "assignedTo": {"type": "string"},
            },
            "required": ["issue_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        issue_id = kwargs["issue_id"]
        payload: dict[str, Any] = {}
        if kwargs.get("status"):
            payload["status"] = kwargs["status"]
        if kwargs.get("assignedTo"):
            payload["assignedTo"] = kwargs["assignedTo"]
        if not payload:
            return ToolResult(
                success=False,
                error="Provide at least one of: status, assignedTo.",
            )
        try:
            status, body = await _request(
                "PUT", f"/issues/{issue_id}/", json_body=payload
            )
            if status != 200 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Issue {body.get('shortId') or issue_id} updated; "
                    f"status={body.get('status')}."
                ),
                data={
                    "id": body.get("id"),
                    "shortId": body.get("shortId"),
                    "status": body.get("status"),
                    "assignedTo": body.get("assignedTo"),
                },
            )
        except Exception as e:
            logger.error("sentry_issue_update failed: %s", e)
            return ToolResult(success=False, error=str(e))


class SentryEventListForIssueTool(BaseTool):
    """List recent events associated with an issue."""

    name = "sentry_event_list_for_issue"
    description = (
        "List recent events for a Sentry issue "
        "(``/issues/{id}/events/``). 'limit' controls page size (default 10). "
        "Use to verify a fix — if no new events arrive after the fix ships, "
        "the issue is genuinely resolved."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
            },
            "required": ["issue_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        issue_id = kwargs["issue_id"]
        params = {"limit": kwargs.get("limit", 10)}
        try:
            status, body = await _request(
                "GET", f"/issues/{issue_id}/events/", params=params
            )
            if status != 200 or not isinstance(body, list):
                return ToolResult(success=False, error=_err(status, body))
            events = [
                {
                    "eventID": e.get("eventID"),
                    "dateCreated": e.get("dateCreated"),
                    "message": e.get("message"),
                    "platform": e.get("platform"),
                    "user": (e.get("user") or {}).get("id")
                    or (e.get("user") or {}).get("email"),
                    "tags": [
                        {"key": t.get("key"), "value": t.get("value")}
                        for t in (e.get("tags") or [])
                    ],
                }
                for e in body
            ]
            return ToolResult(
                success=True,
                output=f"Issue {issue_id} has {len(events)} recent event(s).",
                data={"events": events},
            )
        except Exception as e:
            logger.error("sentry_event_list_for_issue failed: %s", e)
            return ToolResult(success=False, error=str(e))


class SentryBreadcrumbsGetTool(BaseTool):
    """Fetch breadcrumbs from a Sentry event for Seer-style analysis."""

    name = "sentry_breadcrumbs_get"
    description = (
        "Fetch breadcrumbs (the chronological trail of events leading up "
        "to the error) for a Sentry event. If 'event_id' is omitted, uses "
        "the issue's latest event. Breadcrumbs are the Seer-style input "
        "for root-cause hypotheses — examine them before proposing a fix."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "event_id": {"type": "string"},
            },
            "required": ["issue_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        issue_id = kwargs["issue_id"]
        event_id = kwargs.get("event_id")
        try:
            if event_id:
                path = f"/issues/{issue_id}/events/{event_id}/"
            else:
                path = f"/issues/{issue_id}/events/latest/"
            status, body = await _request("GET", path)
            if status != 200 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            # Breadcrumbs live inside an entry with type='breadcrumbs'.
            breadcrumbs: list[dict[str, Any]] = []
            for entry in body.get("entries") or []:
                if entry.get("type") == "breadcrumbs":
                    values = (entry.get("data") or {}).get("values") or []
                    for bc in values:
                        breadcrumbs.append(
                            {
                                "timestamp": bc.get("timestamp"),
                                "category": bc.get("category"),
                                "level": bc.get("level"),
                                "message": bc.get("message"),
                                "type": bc.get("type"),
                                "data": bc.get("data") or {},
                            }
                        )
                    break
            return ToolResult(
                success=True,
                output=(
                    f"Fetched {len(breadcrumbs)} breadcrumb(s) from "
                    f"event {body.get('eventID') or event_id or 'latest'}."
                ),
                data={
                    "eventID": body.get("eventID"),
                    "dateCreated": body.get("dateCreated"),
                    "breadcrumbs": breadcrumbs,
                    "breadcrumb_count": len(breadcrumbs),
                },
            )
        except Exception as e:
            logger.error("sentry_breadcrumbs_get failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_sentry_tools() -> list[BaseTool]:
    """Return the Sentry tool set."""
    return [
        SentryIssueListTool(),
        SentryIssueGetTool(),
        SentryIssueUpdateTool(),
        SentryEventListForIssueTool(),
        SentryBreadcrumbsGetTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    SentryIssueListTool,
    SentryIssueGetTool,
    SentryIssueUpdateTool,
    SentryEventListForIssueTool,
    SentryBreadcrumbsGetTool,
):
    _cls.audience = Audience.PLATFORM
