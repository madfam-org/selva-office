"""Loki log-query tools.

During incident triage the next question after 'what alert fired?' is
'what were the logs saying at that moment?'. Loki is the cluster's log
aggregation store; this module lets an agent run LogQL range queries and
enumerate available label dimensions without shelling into Grafana.

Endpoint defaults to ``http://loki.logging.svc.cluster.local:3100`` (the
in-cluster gateway service). Override via ``LOKI_URL``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

LOKI_URL = os.environ.get("LOKI_URL", "http://loki.logging.svc.cluster.local:3100")


async def _loki_request(
    path: str, params: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | str]:
    url = f"{LOKI_URL.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("message") or body.get("error") or str(body)
    return f"HTTP {status}: {body}"


class LokiQueryRangeTool(BaseTool):
    """LogQL range query against Loki."""

    name = "loki_query_range"
    description = (
        "Execute a LogQL range query (``/loki/api/v1/query_range``). Pass "
        "'query' (LogQL), 'start' + 'end' (RFC3339 or unix nanoseconds), "
        "and optional 'limit' (default 500). Returns log lines grouped by "
        "stream labels with structured timestamps. Use during incident "
        "triage to pull the logs around an alert's 'startsAt'."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "limit": {"type": "integer", "default": 500, "minimum": 1},
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward"],
                    "default": "backward",
                },
            },
            "required": ["query", "start", "end"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        params = {
            "query": kwargs["query"],
            "start": kwargs["start"],
            "end": kwargs["end"],
            "limit": kwargs.get("limit", 500),
            "direction": kwargs.get("direction", "backward"),
        }
        try:
            status, body = await _loki_request("/loki/api/v1/query_range", params=params)
            if status != 200 or not isinstance(body, dict) or body.get("status") != "success":
                return ToolResult(success=False, error=_err(status, body))
            result = (body.get("data") or {}).get("result") or []
            # Flatten into a simpler list: [{labels, entries: [{ts, line}, ...]}]
            streams: list[dict[str, Any]] = []
            line_count = 0
            for stream in result:
                entries = stream.get("values") or []
                line_count += len(entries)
                streams.append(
                    {
                        "labels": stream.get("stream") or {},
                        "entries": [
                            {"timestamp_ns": e[0], "line": e[1]}
                            for e in entries
                            if isinstance(e, list) and len(e) == 2
                        ],
                    }
                )
            return ToolResult(
                success=True,
                output=(f"Loki query returned {len(streams)} stream(s) / {line_count} line(s)."),
                data={
                    "streams": streams,
                    "stream_count": len(streams),
                    "line_count": line_count,
                    "resultType": (body.get("data") or {}).get("resultType"),
                },
            )
        except Exception as e:
            logger.error("loki_query_range failed: %s", e)
            return ToolResult(success=False, error=str(e))


class LokiLabelsTool(BaseTool):
    """Enumerate available Loki label names."""

    name = "loki_labels"
    description = (
        "List all label names currently indexed by Loki "
        "(``/loki/api/v1/labels``). Use to discover which labels are "
        "available for filtering before composing a LogQL query "
        "(e.g. 'namespace', 'pod', 'container', 'app', 'level')."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        params: dict[str, Any] = {}
        if kwargs.get("start"):
            params["start"] = kwargs["start"]
        if kwargs.get("end"):
            params["end"] = kwargs["end"]
        try:
            status, body = await _loki_request("/loki/api/v1/labels", params=params or None)
            if status != 200 or not isinstance(body, dict) or body.get("status") != "success":
                return ToolResult(success=False, error=_err(status, body))
            labels = body.get("data") or []
            return ToolResult(
                success=True,
                output=f"Loki indexed {len(labels)} label name(s).",
                data={"labels": labels},
            )
        except Exception as e:
            logger.error("loki_labels failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_loki_tools() -> list[BaseTool]:
    """Return the Loki tool set."""
    return [
        LokiQueryRangeTool(),
        LokiLabelsTool(),
    ]


# Audience tagging — platform-only tools. Tenant swarms are filtered
# out of these at spec-generation time by ToolRegistry.get_specs(audience=...).
for _cls in (
    LokiQueryRangeTool,
    LokiLabelsTool,
):
    _cls.audience = Audience.PLATFORM
