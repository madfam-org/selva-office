"""Tests for Prometheus + Alertmanager tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.prometheus import (
    PromAlertsActiveTool,
    PromQueryRangeTool,
    PromQueryTool,
    PromSilenceCreateTool,
    get_prometheus_tools,
)


class TestRegistry:
    def test_four_tools_exported(self) -> None:
        names = {t.name for t in get_prometheus_tools()}
        assert names == {
            "prom_query",
            "prom_query_range",
            "prom_alerts_active",
            "prom_silence_create",
        }

    def test_schemas_valid(self) -> None:
        for t in get_prometheus_tools():
            s = t.parameters_schema()
            assert s["type"] == "object"
            assert "properties" in s


# -- prom_query --------------------------------------------------------------


class TestPromQuery:
    @pytest.mark.asyncio
    async def test_instant_query_ok(self) -> None:
        body = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"__name__": "up", "instance": "a"},
                        "value": [1234567890, "1"],
                    },
                    {
                        "metric": {"__name__": "up", "instance": "b"},
                        "value": [1234567890, "0"],
                    },
                ],
            },
        }
        with patch(
            "selva_tools.builtins.prometheus._prom_request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await PromQueryTool().execute(query="up")
            assert r.success is True
            assert len(r.data["result"]) == 2
            assert r.data["resultType"] == "vector"

    @pytest.mark.asyncio
    async def test_prom_returns_error_status(self) -> None:
        with patch(
            "selva_tools.builtins.prometheus._prom_request",
            new=AsyncMock(return_value=(400, {"status": "error", "error": "bad query"})),
        ):
            r = await PromQueryTool().execute(query="invalid[")
            assert r.success is False
            assert "bad query" in (r.error or "")


# -- prom_query_range --------------------------------------------------------


class TestPromQueryRange:
    @pytest.mark.asyncio
    async def test_range_query_counts_points(self) -> None:
        body = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"job": "nexus-api"},
                        "values": [[1, "1"], [2, "1"], [3, "1"]],
                    },
                    {
                        "metric": {"job": "workers"},
                        "values": [[1, "1"], [2, "1"]],
                    },
                ],
            },
        }
        with patch(
            "selva_tools.builtins.prometheus._prom_request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await PromQueryRangeTool().execute(query="up", start="0", end="10", step="1s")
            assert r.success is True
            assert r.data["series_count"] == 2
            assert r.data["point_count"] == 5


# -- prom_alerts_active ------------------------------------------------------


class TestAlertsActive:
    @pytest.mark.asyncio
    async def test_alerts_aggregate_by_severity(self) -> None:
        body = [
            {
                "labels": {"alertname": "PodCrashing", "severity": "critical"},
                "annotations": {"summary": "pod is crashing"},
                "status": {"state": "active"},
                "startsAt": "2026-04-18T16:00:00Z",
                "endsAt": "2026-04-18T17:00:00Z",
                "fingerprint": "abc",
            },
            {
                "labels": {"alertname": "HighMem", "severity": "warning"},
                "annotations": {},
                "status": {"state": "active"},
                "startsAt": "2026-04-18T16:05:00Z",
                "endsAt": "2026-04-18T17:00:00Z",
                "fingerprint": "def",
            },
            {
                "labels": {"alertname": "HighCPU", "severity": "warning"},
                "annotations": {},
                "status": {"state": "active"},
                "startsAt": "2026-04-18T16:10:00Z",
                "endsAt": "2026-04-18T17:00:00Z",
                "fingerprint": "ghi",
            },
        ]
        with patch(
            "selva_tools.builtins.prometheus._prom_request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await PromAlertsActiveTool().execute()
            assert r.success is True
            assert r.data["by_severity"] == {"critical": 1, "warning": 2}
            assert len(r.data["alerts"]) == 3

    @pytest.mark.asyncio
    async def test_alertmanager_5xx_surfaces_error(self) -> None:
        with patch(
            "selva_tools.builtins.prometheus._prom_request",
            new=AsyncMock(return_value=(503, "upstream unreachable")),
        ):
            r = await PromAlertsActiveTool().execute()
            assert r.success is False
            assert "503" in (r.error or "") or "unreachable" in (r.error or "")


# -- prom_silence_create -----------------------------------------------------


class TestSilenceCreate:
    @pytest.mark.asyncio
    async def test_silence_request_shape(self) -> None:
        captured: dict = {}

        async def fake(path, params=None, method="GET", json_body=None, base=None):
            captured["path"] = path
            captured["method"] = method
            captured["json_body"] = json_body
            captured["base"] = base
            return 200, {"silenceID": "SIL-123"}

        with patch("selva_tools.builtins.prometheus._prom_request", new=fake):
            r = await PromSilenceCreateTool().execute(
                matchers=[{"name": "alertname", "value": "PodCrashing"}],
                duration_minutes=30,
                comment="planned rollout",
            )
            assert r.success is True
            assert r.data["silenceID"] == "SIL-123"
            assert captured["method"] == "POST"
            assert captured["path"] == "/api/v2/silences"
            assert captured["json_body"]["comment"] == "planned rollout"
            assert captured["json_body"]["matchers"][0]["isEqual"] is True

    @pytest.mark.asyncio
    async def test_empty_matchers_rejected(self) -> None:
        r = await PromSilenceCreateTool().execute(matchers=[], duration_minutes=10, comment="x")
        assert r.success is False
        assert "matchers" in (r.error or "")

    @pytest.mark.asyncio
    async def test_alertmanager_error_bubbles_up(self) -> None:
        with patch(
            "selva_tools.builtins.prometheus._prom_request",
            new=AsyncMock(return_value=(400, {"message": "bad matcher"})),
        ):
            r = await PromSilenceCreateTool().execute(
                matchers=[{"name": "x", "value": "y"}],
                duration_minutes=10,
                comment="test",
            )
            assert r.success is False
            assert "bad matcher" in (r.error or "")
