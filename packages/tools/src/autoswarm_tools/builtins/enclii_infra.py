"""Enclii infrastructure tools for the Orchestration Node.

All operations flow through the Enclii Switchyard API — agents NEVER
get kubectl directly. Defense in depth: Selva tool validates → Enclii
API enforces RBAC + audit → K8s executes with timeout.

See docs/SWARM_MANIFESTO.md Axiom I (sovereignty) and
docs/NODE_ARCHITECTURE.md (Orchestration Node).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

ENCLII_API_URL = os.environ.get("ENCLII_API_URL", "")
ENCLII_API_TOKEN = os.environ.get("ENCLII_API_TOKEN", "")

# SecOps: command allowlist at Selva tool level (defense in depth)
EXEC_ALLOWED_PREFIXES = [
    "python manage.py migrate",
    "python manage.py showmigrations",
    "python manage.py check",
    "npx prisma migrate deploy",
    "npx prisma migrate status",
    "npx prisma db push",
    "npx tsx scripts/",
    "alembic upgrade",
    "alembic current",
    "node -e",
]


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if ENCLII_API_TOKEN:
        h["Authorization"] = f"Bearer {ENCLII_API_TOKEN}"
    return h


def _check_command_allowed(command: list[str]) -> bool:
    """Defense-in-depth: validate command against Selva-side allowlist."""
    cmd_str = " ".join(command)
    return any(cmd_str.startswith(prefix) for prefix in EXEC_ALLOWED_PREFIXES)


class EncliiExecTool(BaseTool):
    """Execute a command in a running service pod via Enclii API.

    SecOps: admin-only, command allowlist enforced at both Selva and Enclii,
    one-shot only (no interactive shell), 30-minute timeout cap, full audit trail.
    Category: INFRASTRUCTURE_EXEC.
    """

    name = "enclii_exec"
    description = (
        "Execute a command in a running service pod via Enclii. "
        "Only pre-approved commands are allowed (migrations, health checks). "
        "Use for database migrations, schema checks, and diagnostic commands."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_id": {"type": "string", "description": "Enclii service ID or slug"},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command to execute (e.g., ['python', 'manage.py', 'migrate'])",
                },
                "env": {"type": "string", "default": "production", "description": "Environment"},
                "timeout": {"type": "integer", "default": 120, "description": "Timeout in seconds (max 1800)"},
            },
            "required": ["service_id", "command"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not ENCLII_API_URL:
            return ToolResult(success=False, error="ENCLII_API_URL not configured")

        command = kwargs.get("command", [])
        if not _check_command_allowed(command):
            return ToolResult(
                success=False,
                error=f"Command not in allowlist: {' '.join(command)}. Only migrations and diagnostics are permitted.",
            )

        service_id = kwargs.get("service_id", "")
        try:
            async with httpx.AsyncClient(timeout=min(kwargs.get("timeout", 120), 1800) + 10) as client:
                resp = await client.post(
                    f"{ENCLII_API_URL}/v1/services/{service_id}/exec",
                    headers=_headers(),
                    json={
                        "command": command,
                        "timeout": min(kwargs.get("timeout", 120), 1800),
                        "env": kwargs.get("env", "production"),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            exit_code = data.get("exit_code", -1)

            output = f"Exit code: {exit_code}\n"
            if stdout:
                output += f"stdout:\n{stdout[:2000]}\n"
            if stderr:
                output += f"stderr:\n{stderr[:1000]}"

            return ToolResult(success=exit_code == 0, output=output, data=data)
        except httpx.HTTPStatusError as exc:
            return ToolResult(success=False, error=f"Exec failed ({exc.response.status_code}): {exc.response.text[:200]}")
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Exec request failed: {exc}")


class EncliiRestartTool(BaseTool):
    """Trigger a rolling restart of a service via Enclii API.

    Category: DEPLOY (existing, ASK by default).
    """

    name = "enclii_restart"
    description = (
        "Trigger a rolling restart of a service's pods via Enclii. "
        "Use when a service needs to pick up new config or recover from issues."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_id": {"type": "string", "description": "Enclii service ID or slug"},
                "env": {"type": "string", "default": "production"},
                "reason": {"type": "string", "default": "agent-initiated", "description": "Reason for restart"},
            },
            "required": ["service_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not ENCLII_API_URL:
            return ToolResult(success=False, error="ENCLII_API_URL not configured")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ENCLII_API_URL}/v1/services/{kwargs['service_id']}/restart",
                    headers=_headers(),
                    json={"env": kwargs.get("env", "production"), "reason": kwargs.get("reason", "agent-initiated")},
                )
                resp.raise_for_status()
                data = resp.json()

            return ToolResult(success=True, output=f"Restart initiated: {data.get('message', 'OK')}", data=data)
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Restart failed: {exc}")


class EncliiScaleTool(BaseTool):
    """Scale a service's replica count via Enclii API.

    Category: DEPLOY (ASK by default). Replicas capped at 10.
    """

    name = "enclii_scale"
    description = "Scale a service's replica count via Enclii. Replicas capped at 10."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "replicas": {"type": "integer", "minimum": 0, "maximum": 10},
                "env": {"type": "string", "default": "production"},
            },
            "required": ["service_id", "replicas"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not ENCLII_API_URL:
            return ToolResult(success=False, error="ENCLII_API_URL not configured")

        replicas = min(kwargs.get("replicas", 1), 10)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ENCLII_API_URL}/v1/services/{kwargs['service_id']}/scale",
                    headers=_headers(),
                    json={"replicas": replicas, "env": kwargs.get("env", "production")},
                )
                resp.raise_for_status()
                data = resp.json()

            return ToolResult(success=True, output=f"Scaled to {replicas} replicas", data=data)
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Scale failed: {exc}")


class EncliiLogsTool(BaseTool):
    """Fetch recent logs for a service via Enclii API.

    Read-only. Category: API_CALL (ALLOW).
    """

    name = "enclii_logs"
    description = "Fetch recent logs for a service. Read-only, safe to call anytime."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "env": {"type": "string", "default": "production"},
                "lines": {"type": "integer", "default": 50, "maximum": 500},
                "since": {"type": "string", "default": "1h", "description": "Time duration (e.g., 1h, 30m, 24h)"},
            },
            "required": ["service_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not ENCLII_API_URL:
            return ToolResult(success=False, error="ENCLII_API_URL not configured")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{ENCLII_API_URL}/v1/services/{kwargs['service_id']}/logs/history",
                    headers=_headers(),
                    params={
                        "env": kwargs.get("env", "production"),
                        "lines": min(kwargs.get("lines", 50), 500),
                        "since": kwargs.get("since", "1h"),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            logs = data.get("logs", data.get("entries", []))
            if isinstance(logs, list):
                log_text = "\n".join(str(l) for l in logs[-50:])
            else:
                log_text = str(logs)[:3000]

            return ToolResult(success=True, output=f"Logs ({len(logs) if isinstance(logs, list) else '?'} entries):\n{log_text}", data=data)
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Logs fetch failed: {exc}")


class EncliiHealthTool(BaseTool):
    """Get detailed health status of a service via Enclii API.

    Read-only. Category: INFRASTRUCTURE_MONITOR (ALLOW).
    """

    name = "enclii_health"
    description = (
        "Get detailed health status: pod statuses, readiness/liveness probes, "
        "resource usage, and recent errors. Safe to call anytime."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "env": {"type": "string", "default": "production"},
            },
            "required": ["service_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not ENCLII_API_URL:
            return ToolResult(success=False, error="ENCLII_API_URL not configured")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{ENCLII_API_URL}/v1/services/{kwargs['service_id']}/health/detailed",
                    headers=_headers(),
                    params={"env": kwargs.get("env", "production")},
                )
                resp.raise_for_status()
                data = resp.json()

            status = data.get("status", "unknown")
            pods = data.get("pods", [])
            pod_summary = ", ".join(f"{p.get('name', '?')}: {p.get('status', '?')}" for p in pods[:5])

            return ToolResult(
                success=True,
                output=f"Health: {status} | Pods: {pod_summary or 'none'}",
                data=data,
            )
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Health check failed: {exc}")


class EncliiSecretsTool(BaseTool):
    """Manage service environment variables/secrets via Enclii API.

    SecOps: secret values are REDACTED in tool output. Category: SECRET_MANAGEMENT (ASK).
    """

    name = "enclii_secrets"
    description = (
        "List, create, or update environment variables for a service via Enclii. "
        "Secret values are redacted in output for security."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["list", "set", "delete"],
                    "default": "list",
                },
                "key": {"type": "string", "description": "Variable name (required for set/delete)"},
                "value": {"type": "string", "description": "Variable value (required for set)"},
                "is_secret": {"type": "boolean", "default": True, "description": "Mark as secret (redacted in UI)"},
            },
            "required": ["service_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not ENCLII_API_URL:
            return ToolResult(success=False, error="ENCLII_API_URL not configured")

        service_id = kwargs["service_id"]
        action = kwargs.get("action", "list")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                if action == "list":
                    resp = await client.get(
                        f"{ENCLII_API_URL}/v1/services/{service_id}/env-vars",
                        headers=_headers(),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    # Redact secret values
                    vars_list = data.get("env_vars", data if isinstance(data, list) else [])
                    summary = "\n".join(
                        f"  {v.get('key', '?')}={'****' if v.get('is_secret') else v.get('value', '?')}"
                        for v in vars_list
                    )
                    return ToolResult(
                        success=True,
                        output=f"Environment variables ({len(vars_list)}):\n{summary}",
                        data={"count": len(vars_list), "keys": [v.get("key") for v in vars_list]},
                    )

                elif action == "set":
                    key = kwargs.get("key", "")
                    value = kwargs.get("value", "")
                    if not key or not value:
                        return ToolResult(success=False, error="key and value required for set action")
                    resp = await client.post(
                        f"{ENCLII_API_URL}/v1/services/{service_id}/env-vars",
                        headers=_headers(),
                        json={"key": key, "value": value, "is_secret": kwargs.get("is_secret", True)},
                    )
                    resp.raise_for_status()
                    return ToolResult(success=True, output=f"Set {key}=**** (secret)", data=resp.json())

                elif action == "delete":
                    key = kwargs.get("key", "")
                    if not key:
                        return ToolResult(success=False, error="key required for delete action")
                    resp = await client.delete(
                        f"{ENCLII_API_URL}/v1/services/{service_id}/env-vars/{key}",
                        headers=_headers(),
                    )
                    resp.raise_for_status()
                    return ToolResult(success=True, output=f"Deleted {key}")

                else:
                    return ToolResult(success=False, error=f"Unknown action: {action}")

        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Secrets operation failed: {exc}")
