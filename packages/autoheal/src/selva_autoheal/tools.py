"""The agent's toolbox: Enclii reads and Enclii dry-runs, nothing else.

HARD RULE (v1): no production write is expressible here.

- Every ``POST /v1/ops/<domain>/<action>`` is sent with ``"dry_run": true``,
  built by this module; the model never supplies the body. ``dry_run`` false,
  ``reason``-for-apply, ``idempotency_key`` and ``expected_plan`` (the apply
  half of Enclii's plan-hash contract) cannot be passed.
- Only ``(domain, action)`` pairs in :data:`READ_OPS` (reads) and
  :data:`REMEDY_DRY_RUN_OPS` (plans) are allowed. Everything else is refused
  before any network call, and the refusal is audited.
- ``GET`` is allowed only for the paths matched by :data:`GET_PATHS`.
- Nothing that can return a secret is reachable: the ``secrets`` domain, env
  vars, Vault and token routes are denied by name even if a pattern were
  widened by mistake (:data:`DENY_FRAGMENTS`).
- Results are redacted (credential-shaped values) and truncated before the
  model sees them; they are DATA, and the prompt says so.

Enclii's operator contract: ``apps/switchyard-api/internal/api/operator_*``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

#: Reads (sent as dry-run, which is how Enclii serves operator reads).
READ_OPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("inventory", "network-policies"),
        ("inventory", "topology"),
        ("pods", "diagnose"),
        ("pods", "logs"),
        ("apps", "status"),
        ("apps", "diff"),
        ("jobs", "list"),
        ("storage", "pvc"),
        ("policy", "violations"),
    }
)

#: Remedies the agent may PLAN (dry-run → plan hash for a human to apply).
REMEDY_DRY_RUN_OPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pods", "restart"),
        ("apps", "sync"),
    }
)

#: GET paths the agent may read.
GET_PATHS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"^/v1/projects/[a-z0-9][a-z0-9-]{0,62}$",
        r"^/v1/projects/[a-z0-9][a-z0-9-]{0,62}/(services|addons|environments)$",
        r"^/v1/addons/[0-9a-f-]{36}(/events)?$",
        r"^/v1/services/[0-9a-f-]{36}/(status|health/detailed|networking)$",
        r"^/v1/observability/(alerts|health)$",
    )
)

#: Never reachable, whatever the patterns say.
DENY_FRAGMENTS: tuple[str, ...] = (
    "secret",
    "env-vars",
    "vault",
    "token",
    "credential",
    "kubeconfig",
    "exec",
)

#: Args the model may set on an ops call (mapped to Enclii's names).
_ARG_NAMES: dict[str, str] = {
    "target": "target",
    "container": "container",
    "tail_lines": "tailLines",
}

MAX_RESULT_CHARS = 6000
MAX_TAIL_LINES = 300

_REDACT_KV = re.compile(
    r"(?i)(\"?(?:token|secret|password|passwd|api[_-]?key|authorization|private[_-]?key)"
    r"\"?\s*[:=]\s*\"?)([^\"\s,}]+)"
)
_REDACT_BLOB = re.compile(r"[A-Za-z0-9+/=_-]{48,}")


class ToolRefused(Exception):
    """A tool call outside the allowlist. Never reaches the network."""


#: ``transport(method, path, json_body) -> (status, parsed_body)``
Transport = Callable[[str, str, dict[str, Any] | None], Awaitable[tuple[int, Any]]]


def redact(text: str) -> str:
    text = _REDACT_KV.sub(lambda m: m.group(1) + "[redacted]", text)
    return _REDACT_BLOB.sub("[redacted]", text)


def _clip(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    text = redact(text)
    if len(text) > MAX_RESULT_CHARS:
        return text[:MAX_RESULT_CHARS] + f"…[truncated {len(text) - MAX_RESULT_CHARS} chars]"
    return text


def _denied(*parts: str) -> bool:
    joined = " ".join(parts).lower()
    return any(fragment in joined for fragment in DENY_FRAGMENTS)


@dataclass
class ToolOutcome:
    tool: str
    ok: bool
    text: str
    status: int | None = None
    plan_hash: str | None = None
    audit_id: str | None = None
    refused: bool = False
    #: The parsed body before redaction/clipping, for deterministic
    #: signatures only. Never sent to the model.
    data: Any = None


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "enclii_ops_read",
        "description": "Read-only Enclii operator read (sent as dry-run). Allowed (domain, action): "
        + ", ".join(f"{d}/{a}" for d, a in sorted(READ_OPS)),
        "parameters": {
            "domain": "string",
            "action": "string",
            "namespace": "string (optional)",
            "project": "string (optional, Enclii project slug)",
            "target": "string (optional, e.g. a pod name)",
            "container": "string (optional, pods/logs)",
            "tail_lines": f"integer (optional, pods/logs, <= {MAX_TAIL_LINES})",
        },
    },
    {
        "name": "enclii_get",
        "description": "Read-only Enclii GET. Allowed paths: projects, project services/addons/"
        "environments, addon (+events), service status/health/networking, observability.",
        "parameters": {"path": "string, e.g. /v1/projects/<slug>/addons"},
    },
    {
        "name": "enclii_remedy_dry_run",
        "description": "PLAN a remedy as an Enclii dry-run and get its plan hash. Never applies. "
        "Allowed: " + ", ".join(f"{d}/{a}" for d, a in sorted(REMEDY_DRY_RUN_OPS)),
        "parameters": {
            "domain": "string",
            "action": "string",
            "namespace": "string (optional)",
            "project": "string (optional)",
            "target": "string",
        },
    },
]

TOOL_NAMES = frozenset(spec["name"] for spec in TOOL_SPECS)


@dataclass
class Toolbox:
    transport: Transport | None
    audit: list[dict[str, Any]] = field(default_factory=list)

    async def call(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        """Run one tool call. Refusals and errors come back as outcomes, audited."""
        try:
            if name not in TOOL_NAMES:
                raise ToolRefused(f"unknown tool {name!r}")
            if not isinstance(args, dict):
                raise ToolRefused("arguments must be an object")
            if name == "enclii_get":
                outcome = await self._get(args)
            else:
                outcome = await self._ops(name, args)
        except ToolRefused as exc:
            outcome = ToolOutcome(name, False, f"REFUSED: {exc}", refused=True)
        self.audit.append(
            {
                "tool": name,
                "args": {k: str(v)[:200] for k, v in (args or {}).items()}
                if isinstance(args, dict)
                else {},
                "ok": outcome.ok,
                "refused": outcome.refused,
                "status": outcome.status,
                "plan_hash": outcome.plan_hash,
                "audit_id": outcome.audit_id,
            }
        )
        return outcome

    async def _get(self, args: dict[str, Any]) -> ToolOutcome:
        if set(args) - {"path"}:
            raise ToolRefused("enclii_get takes only 'path'")
        path = str(args.get("path", ""))
        if "?" in path or ".." in path or _denied(path):
            raise ToolRefused(f"path not allowed: {path[:120]}")
        if not any(p.match(path) for p in GET_PATHS):
            raise ToolRefused(f"path not allowlisted: {path[:120]}")
        return await self._send("enclii_get", "GET", path, None)

    async def _ops(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        allowed_keys = {"domain", "action", "namespace", "project", *_ARG_NAMES}
        extra = set(args) - allowed_keys
        if extra:
            raise ToolRefused(f"arguments not allowed: {sorted(extra)}")
        domain, action = str(args.get("domain", "")), str(args.get("action", ""))
        if _denied(domain, action):
            raise ToolRefused(f"{domain}/{action} is never reachable")
        pair = (domain, action)
        allow = READ_OPS if name == "enclii_ops_read" else REMEDY_DRY_RUN_OPS
        if pair not in allow:
            raise ToolRefused(f"{domain}/{action} is not allowlisted for {name}")
        scope = {k: str(args[k]) for k in ("namespace", "project") if args.get(k)}
        # Enclii's operator contract takes ``args`` as map[string]string.
        op_args: dict[str, str] = {}
        for ours, theirs in _ARG_NAMES.items():
            if args.get(ours) in (None, ""):
                continue
            if ours == "tail_lines":
                try:
                    op_args[theirs] = str(max(1, min(int(args[ours]), MAX_TAIL_LINES)))
                except (TypeError, ValueError) as exc:
                    raise ToolRefused("tail_lines must be an integer") from exc
            else:
                op_args[theirs] = str(args[ours])[:253]
        if name == "enclii_remedy_dry_run" and not op_args.get("target"):
            raise ToolRefused("a remedy plan needs a target")
        body = {
            "operation": f"ops.{domain}.{action}",
            "dry_run": True,  # the only value this module ever sends
            "scope": scope,
            "args": op_args,
        }
        return await self._send(name, "POST", f"/v1/ops/{domain}/{action}", body)

    @staticmethod
    def _narrow(path: str, body: dict[str, Any] | None, parsed: Any) -> Any:
        """Keep only the asked namespace of a cluster-wide inventory read."""
        namespace = ((body or {}).get("scope") or {}).get("namespace")
        if not namespace or not path.startswith("/v1/ops/inventory/") or not isinstance(
            parsed, dict
        ):
            return parsed
        data = parsed.get("data")
        if isinstance(data, dict) and isinstance(data.get("groups"), list):
            groups = [g for g in data["groups"] if isinstance(g, dict)
                      and g.get("namespace") == namespace]
            parsed = {**parsed, "data": {**data, "groups": groups}}
        return parsed

    async def _send(
        self, name: str, method: str, path: str, body: dict[str, Any] | None
    ) -> ToolOutcome:
        if body is not None and body.get("dry_run") is not True:  # belt and braces
            raise ToolRefused("only dry-run requests are sent")
        if self.transport is None:
            return ToolOutcome(name, False, "Enclii API not configured (ENCLII_API_URL)")
        try:
            status, parsed = await self.transport(method, path, body)
        except Exception as exc:  # network error: an outcome, not a crash
            return ToolOutcome(name, False, f"transport error: {type(exc).__name__}")
        parsed = self._narrow(path, body, parsed)
        plan_hash = audit_id = None
        if isinstance(parsed, dict):
            audit_id = str(parsed.get("audit_id") or "") or None
            data = parsed.get("data")
            if isinstance(data, dict) and data.get("plan_hash"):
                plan_hash = str(data["plan_hash"])
        return ToolOutcome(
            name,
            200 <= status < 300,
            _clip(parsed),
            status=status,
            plan_hash=plan_hash,
            audit_id=audit_id,
            data=parsed,
        )


def httpx_transport(base_url: str, token: str, timeout: float = 20.0) -> Transport:
    """Production transport: Enclii switchyard-api with a bearer token."""
    import httpx

    root = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def send(method: str, path: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.request(method, root + path, json=body, headers=headers)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text[:MAX_RESULT_CHARS]

    return send
