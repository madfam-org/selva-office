"""Prometheus + Alertmanager query tools.

Agents need a first-class surface to ask "what does monitoring actually see
right now?" during incident triage — without shelling into the cluster and
running ad-hoc promtool. This module exposes the standard Prom HTTP API
(``/api/v1/query``, ``/api/v1/query_range``) plus the Alertmanager v2 API for
reading active alerts and creating maintenance silences.

Endpoints default to the in-cluster services:
- Prometheus:   ``http://prometheus.monitoring.svc.cluster.local:9090``
- Alertmanager: ``http://alertmanager.monitoring.svc.cluster.local:9093``

Override via ``PROMETHEUS_URL`` / ``ALERTMANAGER_URL`` env vars for local dev
or cross-cluster queries.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL", "http://prometheus.monitoring.svc.cluster.local:9090"
)
ALERTMANAGER_URL = os.environ.get(
    "ALERTMANAGER_URL",
    "http://alertmanager.monitoring.svc.cluster.local:9093",
)


async def _prom_request(
    path: str,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    base: str | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    """Low-level HTTP call to Prometheus OR Alertmanager.

    Returns (status_code, parsed_body). Never raises — caller inspects status.
    """
    url = f"{(base or PROMETHEUS_URL).rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, params=params, json=json_body)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        # Prometheus error shape: {"status": "error", "error": "...", "errorType": "..."}
        if body.get("status") == "error":
            return body.get("error") or body.get("errorType") or str(body)
        return body.get("message") or str(body)
    return f"HTTP {status}: {body}"


class PromQueryTool(BaseTool):
    """Instant Prometheus query (``/api/v1/query``)."""

    name = "prom_query"
    description = (
        "Execute a Prometheus instant query against the cluster's Prometheus. "
        "Pass a PromQL 'query' string; optional 'time' as RFC3339 or unix "
        "timestamp (default: now). Returns the parsed result vector/scalar. "
        "Use for point-in-time facts like 'current pod count' or 'current "
        "error rate'."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "time": {
                    "type": "string",
                    "description": "RFC3339 or unix timestamp; default now",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        q = kwargs["query"]
        params: dict[str, Any] = {"query": q}
        if kwargs.get("time"):
            params["time"] = kwargs["time"]
        try:
            status, body = await _prom_request("/api/v1/query", params=params)
            if status != 200 or not isinstance(body, dict) or body.get("status") != "success":
                return ToolResult(success=False, error=_err(status, body))
            result = (body.get("data") or {}).get("result") or []
            rtype = (body.get("data") or {}).get("resultType")
            return ToolResult(
                success=True,
                output=f"Prometheus query returned {len(result)} series (resultType={rtype}).",
                data={"resultType": rtype, "result": result},
            )
        except Exception as e:
            logger.error("prom_query failed: %s", e)
            return ToolResult(success=False, error=str(e))


class PromQueryRangeTool(BaseTool):
    """Range Prometheus query (``/api/v1/query_range``)."""

    name = "prom_query_range"
    description = (
        "Execute a PromQL range query between 'start' and 'end' at 'step' "
        "resolution. Times are RFC3339 or unix timestamps. Step is a "
        "duration string like '30s', '1m', '5m'. Use to graph trends or "
        "compute deltas over an incident window."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "step": {"type": "string", "default": "1m"},
            },
            "required": ["query", "start", "end"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        params = {
            "query": kwargs["query"],
            "start": kwargs["start"],
            "end": kwargs["end"],
            "step": kwargs.get("step", "1m"),
        }
        try:
            status, body = await _prom_request("/api/v1/query_range", params=params)
            if status != 200 or not isinstance(body, dict) or body.get("status") != "success":
                return ToolResult(success=False, error=_err(status, body))
            result = (body.get("data") or {}).get("result") or []
            # Collapse long value lists in the summary; keep raw in data.
            total_points = sum(len(r.get("values") or []) for r in result)
            return ToolResult(
                success=True,
                output=(
                    f"Range query returned {len(result)} series / "
                    f"{total_points} points."
                ),
                data={
                    "resultType": (body.get("data") or {}).get("resultType"),
                    "result": result,
                    "series_count": len(result),
                    "point_count": total_points,
                },
            )
        except Exception as e:
            logger.error("prom_query_range failed: %s", e)
            return ToolResult(success=False, error=str(e))


class PromAlertsActiveTool(BaseTool):
    """List currently active alerts from Alertmanager."""

    name = "prom_alerts_active"
    description = (
        "Read active alerts from Alertmanager (``/api/v2/alerts``). Returns "
        "firing + pending alerts grouped by labels, with severity + start "
        "time + summary. This is the 'what is on fire right now' query — "
        "start incident triage here."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "silenced": {"type": "boolean", "default": False},
                "inhibited": {"type": "boolean", "default": False},
                "active": {"type": "boolean", "default": True},
                "filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alertmanager matcher filters like 'severity=critical'",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        params: dict[str, Any] = {
            "silenced": str(kwargs.get("silenced", False)).lower(),
            "inhibited": str(kwargs.get("inhibited", False)).lower(),
            "active": str(kwargs.get("active", True)).lower(),
        }
        if kwargs.get("filter"):
            params["filter"] = kwargs["filter"]
        try:
            status, body = await _prom_request(
                "/api/v2/alerts", params=params, base=ALERTMANAGER_URL
            )
            if status != 200 or not isinstance(body, list):
                return ToolResult(success=False, error=_err(status, body))
            alerts = [
                {
                    "labels": a.get("labels") or {},
                    "annotations": a.get("annotations") or {},
                    "status": (a.get("status") or {}).get("state"),
                    "startsAt": a.get("startsAt"),
                    "endsAt": a.get("endsAt"),
                    "fingerprint": a.get("fingerprint"),
                }
                for a in body
            ]
            severities: dict[str, int] = {}
            for a in alerts:
                sev = (a["labels"] or {}).get("severity", "unknown")
                severities[sev] = severities.get(sev, 0) + 1
            return ToolResult(
                success=True,
                output=(
                    f"{len(alerts)} active alert(s); "
                    f"by severity: {severities or 'none'}"
                ),
                data={"alerts": alerts, "by_severity": severities},
            )
        except Exception as e:
            logger.error("prom_alerts_active failed: %s", e)
            return ToolResult(success=False, error=str(e))


class PromSilenceCreateTool(BaseTool):
    """Create an Alertmanager silence (planned maintenance)."""

    name = "prom_silence_create"
    description = (
        "Create an Alertmanager silence covering the given matchers for "
        "'duration_minutes'. Matchers are a list of "
        "{name, value, isRegex}. Use before planned maintenance / rollouts "
        "to suppress known-transient alerts. Returns the silence id."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "matchers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "value": {"type": "string"},
                            "isRegex": {"type": "boolean", "default": False},
                        },
                        "required": ["name", "value"],
                    },
                },
                "duration_minutes": {"type": "integer", "minimum": 1},
                "comment": {"type": "string"},
                "created_by": {"type": "string", "default": "selva"},
            },
            "required": ["matchers", "duration_minutes", "comment"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        matchers = kwargs["matchers"]
        if not isinstance(matchers, list) or not matchers:
            return ToolResult(
                success=False, error="matchers must be a non-empty list."
            )
        now = datetime.now(timezone.utc)
        ends = now + timedelta(minutes=int(kwargs["duration_minutes"]))
        payload = {
            "matchers": [
                {
                    "name": m["name"],
                    "value": m["value"],
                    "isRegex": bool(m.get("isRegex", False)),
                    "isEqual": True,
                }
                for m in matchers
            ],
            "startsAt": now.isoformat().replace("+00:00", "Z"),
            "endsAt": ends.isoformat().replace("+00:00", "Z"),
            "createdBy": kwargs.get("created_by", "selva"),
            "comment": kwargs["comment"],
        }
        try:
            status, body = await _prom_request(
                "/api/v2/silences",
                method="POST",
                json_body=payload,
                base=ALERTMANAGER_URL,
            )
            if status not in (200, 201) or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=(
                    f"Silence created; expires "
                    f"{ends.isoformat().replace('+00:00', 'Z')}."
                ),
                data={
                    "silenceID": body.get("silenceID"),
                    "endsAt": payload["endsAt"],
                    "matchers": payload["matchers"],
                },
            )
        except Exception as e:
            logger.error("prom_silence_create failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_prometheus_tools() -> list[BaseTool]:
    """Return the Prometheus + Alertmanager tool set."""
    return [
        PromQueryTool(),
        PromQueryRangeTool(),
        PromAlertsActiveTool(),
        PromSilenceCreateTool(),
    ]
