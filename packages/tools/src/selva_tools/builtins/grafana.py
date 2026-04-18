"""Grafana read-only dashboard + panel tools.

For incident reports + post-mortems the swarm needs to embed an actual
graph, not just a Prom query result. Grafana's rendering endpoint (from
the Renderer plugin / image-renderer sidecar) produces a PNG of any panel
over a given time window — this module wraps it.

We keep the surface deliberately read-only. Dashboard CRUD is intentionally
not exposed here — those changes should go through the dashboards-as-code
repo, not an agent tool.

Env: ``GRAFANA_URL`` (e.g. ``https://grafana.madfam.io``),
``GRAFANA_API_TOKEN`` (a Viewer- or Editor-scoped API token).
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

GRAFANA_URL = os.environ.get("GRAFANA_URL", "")
GRAFANA_API_TOKEN = os.environ.get("GRAFANA_API_TOKEN", "")


def _creds_check() -> str | None:
    if not GRAFANA_URL:
        return "GRAFANA_URL must be set."
    if not GRAFANA_API_TOKEN:
        return "GRAFANA_API_TOKEN must be set."
    return None


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {GRAFANA_API_TOKEN}",
        "Accept": "application/json",
    }


async def _json_request(
    method: str, path: str, params: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    url = f"{GRAFANA_URL.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method, url, headers=_headers(), params=params
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("message") or body.get("error") or str(body)
    return f"HTTP {status}: {body}"


class GrafanaDashboardListTool(BaseTool):
    """List Grafana dashboards (search ``/api/search``)."""

    name = "grafana_dashboard_list"
    description = (
        "List Grafana dashboards via ``/api/search?type=dash-db``. Filter "
        "by 'folder_id', 'tag' (repeatable), or 'query' substring. Returns "
        "uid + title + tags + folder — use the uid with grafana_panel_export "
        "to render a panel from one of them."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_id": {"type": "integer"},
                "query": {"type": "string"},
                "tag": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 5000},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        params: dict[str, Any] = {
            "type": "dash-db",
            "limit": kwargs.get("limit", 100),
        }
        if kwargs.get("folder_id") is not None:
            params["folderIds"] = kwargs["folder_id"]
        if kwargs.get("query"):
            params["query"] = kwargs["query"]
        if kwargs.get("tag"):
            params["tag"] = kwargs["tag"]
        try:
            status, body = await _json_request("GET", "/api/search", params=params)
            if status != 200 or not isinstance(body, list):
                return ToolResult(success=False, error=_err(status, body))
            dashboards = [
                {
                    "id": d.get("id"),
                    "uid": d.get("uid"),
                    "title": d.get("title"),
                    "url": d.get("url"),
                    "tags": d.get("tags") or [],
                    "folderId": d.get("folderId"),
                    "folderTitle": d.get("folderTitle"),
                }
                for d in body
            ]
            return ToolResult(
                success=True,
                output=f"Grafana returned {len(dashboards)} dashboard(s).",
                data={"dashboards": dashboards},
            )
        except Exception as e:
            logger.error("grafana_dashboard_list failed: %s", e)
            return ToolResult(success=False, error=str(e))


class GrafanaPanelExportTool(BaseTool):
    """Render one panel from one dashboard as a PNG image."""

    name = "grafana_panel_export"
    description = (
        "Render a single panel (``/render/d-solo/{uid}?panelId={id}``) as "
        "PNG using Grafana's image-renderer. 'from_time' / 'to_time' are "
        "Grafana time refs — either unix ms or relative like 'now-1h'. "
        "Returns 'image_base64' (raw PNG bytes base64-encoded) plus a "
        "stable 'snapshot_url' pointing at the solo-panel view for embed "
        "in reports. Requires the image-renderer plugin on the Grafana "
        "side; if it isn't installed the tool returns the URL only."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dashboard_uid": {"type": "string"},
                "panel_id": {"type": "integer"},
                "from_time": {"type": "string"},
                "to_time": {"type": "string", "default": "now"},
                "width": {"type": "integer", "default": 1000, "minimum": 100, "maximum": 4000},
                "height": {"type": "integer", "default": 500, "minimum": 100, "maximum": 4000},
                "org_id": {"type": "integer", "default": 1},
            },
            "required": ["dashboard_uid", "panel_id", "from_time"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _creds_check()
        if err:
            return ToolResult(success=False, error=err)
        uid = kwargs["dashboard_uid"]
        panel_id = int(kwargs["panel_id"])
        params = {
            "panelId": panel_id,
            "from": kwargs["from_time"],
            "to": kwargs.get("to_time", "now"),
            "width": kwargs.get("width", 1000),
            "height": kwargs.get("height", 500),
            "orgId": kwargs.get("org_id", 1),
        }
        url = f"{GRAFANA_URL.rstrip('/')}/render/d-solo/{uid}"
        snapshot_url = f"{GRAFANA_URL.rstrip('/')}/d-solo/{uid}?panelId={panel_id}"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {GRAFANA_API_TOKEN}"},
                    params=params,
                )
                ct = resp.headers.get("content-type", "")
                if resp.status_code != 200 or "image" not in ct:
                    # Fall back to snapshot-url-only so the caller still
                    # gets something useful to embed.
                    return ToolResult(
                        success=True,
                        output=(
                            "Image renderer unavailable; returning "
                            "snapshot URL only."
                        ),
                        data={
                            "snapshot_url": snapshot_url,
                            "image_base64": None,
                            "render_error": f"HTTP {resp.status_code} content-type={ct}",
                        },
                    )
                image_b64 = base64.b64encode(resp.content).decode("ascii")
                return ToolResult(
                    success=True,
                    output=(
                        f"Rendered panel {panel_id} of dashboard {uid} "
                        f"({len(resp.content)} bytes PNG)."
                    ),
                    data={
                        "image_base64": image_b64,
                        "snapshot_url": snapshot_url,
                        "content_type": ct,
                        "bytes": len(resp.content),
                    },
                )
        except Exception as e:
            logger.error("grafana_panel_export failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_grafana_tools() -> list[BaseTool]:
    """Return the Grafana tool set."""
    return [
        GrafanaDashboardListTool(),
        GrafanaPanelExportTool(),
    ]
