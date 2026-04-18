"""ArgoCD Application management tools.

Talks directly to the argocd-server in-cluster service. Uses a token mounted
via the ``ARGOCD_AUTH_TOKEN`` env var (provisioned from the
``argocd-token-selva`` secret). Falls through to unauthenticated calls for
read-only endpoints when the token isn't present, to keep local dev usable.

This module closes the ops-layer gap that required raw ``kubectl patch
application`` commands during the 2026-04-18 outage recovery: agents can now
trigger syncs, hard-refreshes, and read status without a shell escape.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

ARGOCD_SERVER = os.environ.get(
    "ARGOCD_SERVER", "https://argocd-server.argocd.svc.cluster.local"
)
ARGOCD_TOKEN = os.environ.get("ARGOCD_AUTH_TOKEN", "")


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if ARGOCD_TOKEN:
        h["Authorization"] = f"Bearer {ARGOCD_TOKEN}"
    return h


async def _request(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[dict[str, Any]] | str]:
    """Low-level Argo CD API call; returns (status_code, parsed_body)."""
    url = f"{ARGOCD_SERVER.rstrip('/')}{path}"
    # argocd-server runs with its own self-signed in-cluster cert; verify=False
    # is fine when we're reaching it through cluster DNS.
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        resp = await client.request(
            method, url, headers=_headers(), json=json_body, params=params
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body


def _err(status: int, body: Any) -> str:
    if isinstance(body, dict):
        return body.get("message") or str(body.get("error") or body)
    return f"HTTP {status}: {body}"


class ArgocdListAppsTool(BaseTool):
    """List ArgoCD Applications, optionally filtered by project, namespace, name."""

    name = "argocd_list_apps"
    description = (
        "List Argo CD Applications with sync + health status. Filter by "
        "'project', 'namespace' (the app's destination namespace), or a "
        "'name' substring. Returns a compact summary — use argocd_get_app "
        "for full detail."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "namespace": {"type": "string"},
                "name_contains": {"type": "string"},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            status, body = await _request("GET", "/api/v1/applications")
            if status != 200 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            items = body.get("items") or []
            if kwargs.get("project"):
                items = [
                    a
                    for a in items
                    if (a.get("spec") or {}).get("project") == kwargs["project"]
                ]
            if kwargs.get("namespace"):
                items = [
                    a
                    for a in items
                    if (a.get("spec") or {}).get("destination", {}).get(
                        "namespace"
                    )
                    == kwargs["namespace"]
                ]
            if kwargs.get("name_contains"):
                needle = kwargs["name_contains"].lower()
                items = [
                    a
                    for a in items
                    if needle in (a.get("metadata", {}).get("name", "")).lower()
                ]
            summary = [
                {
                    "name": (a.get("metadata") or {}).get("name"),
                    "project": (a.get("spec") or {}).get("project"),
                    "namespace": (a.get("spec") or {})
                    .get("destination", {})
                    .get("namespace"),
                    "sync": (a.get("status") or {}).get("sync", {}).get("status"),
                    "health": (a.get("status") or {})
                    .get("health", {})
                    .get("status"),
                    "revision": (a.get("status") or {}).get("sync", {}).get("revision"),
                }
                for a in items
            ]
            return ToolResult(
                success=True,
                output=f"Found {len(summary)} Application(s).",
                data={"applications": summary},
            )
        except Exception as e:
            logger.error("argocd_list_apps failed: %s", e)
            return ToolResult(success=False, error=str(e))


class ArgocdGetAppTool(BaseTool):
    """Get full status + resources for one ArgoCD Application."""

    name = "argocd_get_app"
    description = (
        "Fetch a single Argo CD Application's full state: sync + health, "
        "last-sync conditions (useful for diagnosing Kyverno admission "
        "denials), operation history, and the list of managed resources "
        "with per-resource sync status."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs["name"]
        try:
            status, body = await _request("GET", f"/api/v1/applications/{name}")
            if status != 200 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            st = body.get("status") or {}
            conditions = st.get("conditions") or []
            resources = st.get("resources") or []
            return ToolResult(
                success=True,
                output=(
                    f"{name}: sync={st.get('sync', {}).get('status')} "
                    f"health={st.get('health', {}).get('status')} "
                    f"revision={st.get('sync', {}).get('revision')}"
                ),
                data={
                    "sync": st.get("sync"),
                    "health": st.get("health"),
                    "conditions": [
                        {
                            "type": c.get("type"),
                            "message": c.get("message", "")[:500],
                        }
                        for c in conditions
                    ],
                    "resources": [
                        {
                            "kind": r.get("kind"),
                            "name": r.get("name"),
                            "namespace": r.get("namespace"),
                            "status": r.get("status"),
                            "health": (r.get("health") or {}).get("status"),
                        }
                        for r in resources
                    ],
                },
            )
        except Exception as e:
            logger.error("argocd_get_app failed: %s", e)
            return ToolResult(success=False, error=str(e))


class ArgocdSyncAppTool(BaseTool):
    """Trigger an Argo CD sync for an Application."""

    name = "argocd_sync_app"
    description = (
        "Trigger a sync on an Argo CD Application. Optional 'revision' "
        "targets a specific git ref (default: the tracked branch). 'prune' "
        "deletes resources that are no longer in git. 'force' ignores "
        "sync-windows. This is the tool equivalent of the "
        "'kubectl patch application <name> --type merge -p ...' pattern."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "revision": {"type": "string"},
                "prune": {"type": "boolean", "default": False},
                "force": {"type": "boolean", "default": False},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs["name"]
        payload: dict[str, Any] = {
            "prune": kwargs.get("prune", False),
            "dryRun": kwargs.get("dry_run", False),
            "strategy": {"apply": {"force": kwargs.get("force", False)}},
        }
        if kwargs.get("revision"):
            payload["revision"] = kwargs["revision"]
        try:
            status, body = await _request(
                "POST", f"/api/v1/applications/{name}/sync", json_body=payload
            )
            if status != 200 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"Sync triggered on {name}.",
                data={
                    "operation": (body.get("operation") or {}),
                    "revision": kwargs.get("revision"),
                },
            )
        except Exception as e:
            logger.error("argocd_sync_app failed: %s", e)
            return ToolResult(success=False, error=str(e))


class ArgocdRefreshAppTool(BaseTool):
    """Refresh an ArgoCD Application (hard = re-evaluate manifests + drift)."""

    name = "argocd_refresh_app"
    description = (
        "Refresh an Argo CD Application. 'hard' (default) re-evaluates git "
        "manifests AND re-compares against live cluster state — use this "
        "when you've just merged a commit and want Argo to pick it up now "
        "instead of waiting for the 3-minute poll. 'normal' only re-fetches "
        "live state."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["normal", "hard"],
                    "default": "hard",
                },
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs["name"]
        refresh_type = kwargs.get("type", "hard")
        try:
            # GET /api/v1/applications/{name}?refresh=hard
            status, body = await _request(
                "GET",
                f"/api/v1/applications/{name}",
                params={"refresh": refresh_type},
            )
            if status != 200 or not isinstance(body, dict):
                return ToolResult(success=False, error=_err(status, body))
            return ToolResult(
                success=True,
                output=f"Refresh ({refresh_type}) requested on {name}.",
                data={"name": name, "refresh_type": refresh_type},
            )
        except Exception as e:
            logger.error("argocd_refresh_app failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_argocd_tools() -> list[BaseTool]:
    """Return the Argo CD tool set."""
    return [
        ArgocdListAppsTool(),
        ArgocdGetAppTool(),
        ArgocdSyncAppTool(),
        ArgocdRefreshAppTool(),
    ]


# Audience tagging — platform infra (sync app state, trigger reconciliation).
# Tenant swarms must not see these.
for _cls in (
    ArgocdListAppsTool,
    ArgocdGetAppTool,
    ArgocdSyncAppTool,
    ArgocdRefreshAppTool,
):
    _cls.audience = Audience.PLATFORM
