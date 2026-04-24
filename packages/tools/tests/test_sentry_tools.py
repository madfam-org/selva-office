"""Tests for Sentry issue + event tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.sentry import (
    SentryBreadcrumbsGetTool,
    SentryEventListForIssueTool,
    SentryIssueGetTool,
    SentryIssueListTool,
    SentryIssueUpdateTool,
    get_sentry_tools,
)


class TestRegistry:
    def test_five_tools_exported(self) -> None:
        names = {t.name for t in get_sentry_tools()}
        assert names == {
            "sentry_issue_list",
            "sentry_issue_get",
            "sentry_issue_update",
            "sentry_event_list_for_issue",
            "sentry_breadcrumbs_get",
        }

    def test_schemas_valid(self) -> None:
        for t in get_sentry_tools():
            s = t.parameters_schema()
            assert s["type"] == "object"


# -- credential absence ------------------------------------------------------


class TestCredsAbsence:
    @pytest.mark.asyncio
    async def test_list_without_token_returns_error(self) -> None:
        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", ""),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
        ):
            r = await SentryIssueListTool().execute(project_slug="fortuna")
            assert r.success is False
            assert "SENTRY_API_TOKEN" in (r.error or "")

    @pytest.mark.asyncio
    async def test_get_without_org_returns_error(self) -> None:
        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", ""),
        ):
            r = await SentryIssueGetTool().execute(issue_id="1")
            assert r.success is False
            assert "SENTRY_ORG_SLUG" in (r.error or "")


# -- issue list --------------------------------------------------------------


class TestIssueList:
    @pytest.mark.asyncio
    async def test_list_summarizes_issues(self) -> None:
        body = [
            {
                "id": "1",
                "shortId": "FORTUNA-1",
                "title": "KeyError: 'user_id'",
                "culprit": "fortuna.routers.dispatch",
                "status": "unresolved",
                "level": "error",
                "count": 12,
                "userCount": 3,
                "firstSeen": "2026-04-18T10:00:00Z",
                "lastSeen": "2026-04-18T16:00:00Z",
                "permalink": "https://sentry.io/...",
            }
        ]
        captured: dict = {}

        async def fake(method, path, params=None, json_body=None):
            captured["path"] = path
            captured["params"] = params
            return 200, body

        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch("selva_tools.builtins.sentry._request", new=fake),
        ):
            r = await SentryIssueListTool().execute(
                project_slug="fortuna", status="unresolved", query="level:error"
            )
            assert r.success is True
            assert r.data["issues"][0]["shortId"] == "FORTUNA-1"
            assert "is:unresolved" in captured["params"]["query"]
            assert "level:error" in captured["params"]["query"]
            assert "/madfam/fortuna/" in captured["path"]

    @pytest.mark.asyncio
    async def test_list_unauthorized_error(self) -> None:
        async def fake(method, path, params=None, json_body=None):
            return 401, {"detail": "authentication failed"}

        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch("selva_tools.builtins.sentry._request", new=fake),
        ):
            r = await SentryIssueListTool().execute(project_slug="fortuna")
            assert r.success is False
            assert "authentication" in (r.error or "")


# -- issue get ---------------------------------------------------------------


class TestIssueGet:
    @pytest.mark.asyncio
    async def test_returns_compact_projection(self) -> None:
        body = {
            "id": "42",
            "shortId": "SELVA-42",
            "title": "timeout",
            "culprit": "m.f",
            "status": "unresolved",
            "level": "warning",
            "platform": "python",
            "assignedTo": None,
            "count": 3,
            "userCount": 1,
            "firstSeen": "2026-04-18T16:00:00Z",
            "lastSeen": "2026-04-18T17:00:00Z",
            "permalink": "https://sentry.io/...",
            "tags": [],
            "stats": {"24h": [[1, 0]]},
            "metadata": {"type": "TimeoutError"},
        }
        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch(
                "selva_tools.builtins.sentry._request",
                new=AsyncMock(return_value=(200, body)),
            ),
        ):
            r = await SentryIssueGetTool().execute(issue_id="42")
            assert r.success is True
            assert r.data["shortId"] == "SELVA-42"
            assert r.data["metadata"]["type"] == "TimeoutError"


# -- issue update ------------------------------------------------------------


class TestIssueUpdate:
    @pytest.mark.asyncio
    async def test_resolve(self) -> None:
        captured: dict = {}

        async def fake(method, path, params=None, json_body=None):
            captured["method"] = method
            captured["path"] = path
            captured["json_body"] = json_body
            return 200, {
                "id": "42",
                "shortId": "SELVA-42",
                "status": "resolved",
                "assignedTo": None,
            }

        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch("selva_tools.builtins.sentry._request", new=fake),
        ):
            r = await SentryIssueUpdateTool().execute(issue_id="42", status="resolved")
            assert r.success is True
            assert captured["method"] == "PUT"
            assert captured["json_body"] == {"status": "resolved"}
            assert r.data["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_update_without_fields_errors(self) -> None:
        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
        ):
            r = await SentryIssueUpdateTool().execute(issue_id="42")
            assert r.success is False
            assert "at least one" in (r.error or "").lower()


# -- events ------------------------------------------------------------------


class TestEventList:
    @pytest.mark.asyncio
    async def test_events_compact(self) -> None:
        body = [
            {
                "eventID": "eA",
                "dateCreated": "2026-04-18T16:00:00Z",
                "message": "boom",
                "platform": "python",
                "user": {"id": "u1", "email": "u@x.com"},
                "tags": [{"key": "env", "value": "prod"}],
            }
        ]
        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch(
                "selva_tools.builtins.sentry._request",
                new=AsyncMock(return_value=(200, body)),
            ),
        ):
            r = await SentryEventListForIssueTool().execute(issue_id="42")
            assert r.success is True
            assert r.data["events"][0]["eventID"] == "eA"
            assert r.data["events"][0]["user"] == "u1"

    @pytest.mark.asyncio
    async def test_events_error(self) -> None:
        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch(
                "selva_tools.builtins.sentry._request",
                new=AsyncMock(return_value=(404, {"detail": "not found"})),
            ),
        ):
            r = await SentryEventListForIssueTool().execute(issue_id="42")
            assert r.success is False


# -- breadcrumbs -------------------------------------------------------------


class TestBreadcrumbs:
    @pytest.mark.asyncio
    async def test_breadcrumbs_parses_entries(self) -> None:
        body = {
            "eventID": "eB",
            "dateCreated": "2026-04-18T16:00:00Z",
            "entries": [
                {"type": "exception", "data": {}},
                {
                    "type": "breadcrumbs",
                    "data": {
                        "values": [
                            {
                                "timestamp": "2026-04-18T15:59:58Z",
                                "category": "http",
                                "level": "info",
                                "message": "GET /api/v1/x",
                                "type": "http",
                            },
                            {
                                "timestamp": "2026-04-18T15:59:59Z",
                                "category": "db",
                                "level": "warning",
                                "message": "slow query",
                                "type": "query",
                            },
                        ]
                    },
                },
            ],
        }

        async def fake(method, path, params=None, json_body=None):
            assert path.endswith("/events/latest/")
            return 200, body

        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch("selva_tools.builtins.sentry._request", new=fake),
        ):
            r = await SentryBreadcrumbsGetTool().execute(issue_id="42")
            assert r.success is True
            assert r.data["breadcrumb_count"] == 2
            assert r.data["breadcrumbs"][0]["category"] == "http"

    @pytest.mark.asyncio
    async def test_breadcrumbs_explicit_event_id(self) -> None:
        captured: dict = {}

        async def fake(method, path, params=None, json_body=None):
            captured["path"] = path
            return 200, {"eventID": "eX", "entries": []}

        with (
            patch("selva_tools.builtins.sentry.SENTRY_API_TOKEN", "tok"),
            patch("selva_tools.builtins.sentry.SENTRY_ORG_SLUG", "madfam"),
            patch("selva_tools.builtins.sentry._request", new=fake),
        ):
            await SentryBreadcrumbsGetTool().execute(issue_id="42", event_id="eX")
            assert captured["path"].endswith("/events/eX/")
