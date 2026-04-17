"""Individual check implementations + the aggregated report type.

Each check is an async callable that returns a :class:`Check` describing
its outcome. Checks are intentionally small and composable — the runner
executes them in parallel when safe, serial when they depend on each
other.

Check authors must:

    * Never raise. Wrap all failures into a ``Check`` with
      ``status=CheckStatus.FAIL`` and a short ``detail``.
    * Complete within ~3 seconds. Anything slower goes behind a
      ``--slow`` gate at the CLI layer (reserved; not implemented v1).
    * Classify: PASS / WARN / FAIL / SKIP.
      WARN means "works but you'll regret it later" (e.g. insecure
      default, stale token). FAIL means "don't start work".
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable

import httpx


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class Check:
    name: str
    status: CheckStatus
    detail: str
    duration_ms: float = 0.0
    remediation: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)

    def is_blocker(self) -> bool:
        return self.status is CheckStatus.FAIL


@dataclass
class DoctorReport:
    checks: list[Check]
    started_at: float
    finished_at: float

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000.0

    @property
    def ok(self) -> bool:
        return not any(c.is_blocker() for c in self.checks)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status is CheckStatus.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status is CheckStatus.WARN)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fail_count": self.fail_count,
            "warn_count": self.warn_count,
            "duration_ms": round(self.duration_ms, 2),
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "detail": c.detail,
                    "duration_ms": round(c.duration_ms, 2),
                    "remediation": c.remediation,
                    "facts": c.facts,
                }
                for c in self.checks
            ],
        }

    def to_text(self) -> str:
        symbols = {
            CheckStatus.PASS: "✓",
            CheckStatus.WARN: "!",
            CheckStatus.FAIL: "✗",
            CheckStatus.SKIP: "·",
        }
        lines = []
        for c in self.checks:
            lines.append(f"  {symbols[c.status]} {c.name:<32} {c.detail}")
            if c.remediation and c.status is not CheckStatus.PASS:
                lines.append(f"      → {c.remediation}")
        header = (
            f"OK" if self.ok else f"NOT READY ({self.fail_count} fail, {self.warn_count} warn)"
        )
        return f"[autoswarm-doctor] {header}\n" + "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# --- Individual check implementations -------------------------------------


async def check_env_vars() -> Check:
    """Verify the env vars Selva needs to exist (but not necessarily be non-empty)."""
    t0 = time.perf_counter()
    required = [
        "DATABASE_URL",
        "REDIS_URL",
    ]
    recommended = [
        "SELVA_API_BASE",
        "SELVA_API_KEY",
        "ENCLII_API_URL",
        "ENCLII_API_TOKEN",
    ]
    missing_required = [k for k in required if not os.environ.get(k)]
    missing_recommended = [k for k in recommended if not os.environ.get(k)]

    dur = (time.perf_counter() - t0) * 1000.0
    if missing_required:
        return Check(
            name="env.required",
            status=CheckStatus.FAIL,
            detail=f"missing: {', '.join(missing_required)}",
            duration_ms=dur,
            remediation="Populate these env vars before starting a task (see CLAUDE.md).",
        )
    if missing_recommended:
        return Check(
            name="env.required",
            status=CheckStatus.WARN,
            detail=f"required OK; recommended missing: {', '.join(missing_recommended)}",
            duration_ms=dur,
            remediation="Recommended vars unlock ops tools (inference, enclii). Worker may partially function without them.",
            facts={"missing_recommended": missing_recommended},
        )
    return Check(
        name="env.required",
        status=CheckStatus.PASS,
        detail="all required + recommended env vars present",
        duration_ms=dur,
    )


async def check_binary(
    binary: str, required: bool = True, purpose: str | None = None
) -> Check:
    """Generic binary-on-PATH check. Reused for enclii, git, gh, kubectl."""
    t0 = time.perf_counter()
    path = shutil.which(binary)
    dur = (time.perf_counter() - t0) * 1000.0
    name = f"binary.{binary}"
    if path is None:
        return Check(
            name=name,
            status=CheckStatus.FAIL if required else CheckStatus.WARN,
            detail=f"{binary!r} not on PATH",
            duration_ms=dur,
            remediation=(
                f"Install {binary} in the worker image"
                + (f" — needed for {purpose}" if purpose else "")
            ),
        )
    return Check(
        name=name,
        status=CheckStatus.PASS,
        detail=path,
        duration_ms=dur,
        facts={"path": path},
    )


async def check_selva_reachable() -> Check:
    """Hit SELVA_API_BASE's health path (or /models) with a short timeout."""
    t0 = time.perf_counter()
    base = os.environ.get("SELVA_API_BASE", "").rstrip("/")
    key = os.environ.get("SELVA_API_KEY")
    dur = lambda: (time.perf_counter() - t0) * 1000.0

    if not base:
        return Check(
            name="selva.reachable",
            status=CheckStatus.SKIP,
            detail="SELVA_API_BASE not set",
            duration_ms=dur(),
        )

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    # Selva's proxy exposes /models — 200 is success, 401 means auth bad.
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base}/models", headers=headers)
    except httpx.HTTPError as exc:
        return Check(
            name="selva.reachable",
            status=CheckStatus.FAIL,
            detail=f"unreachable: {type(exc).__name__}: {exc}",
            duration_ms=dur(),
            remediation="Check SELVA_API_BASE; verify network egress to the Selva service.",
        )

    if resp.status_code == 401:
        return Check(
            name="selva.reachable",
            status=CheckStatus.FAIL,
            detail="SELVA_API_KEY rejected (HTTP 401)",
            duration_ms=dur(),
            remediation="Rotate SELVA_API_KEY and redeploy.",
        )
    if resp.status_code >= 500:
        return Check(
            name="selva.reachable",
            status=CheckStatus.FAIL,
            detail=f"Selva 5xx at /models: {resp.status_code}",
            duration_ms=dur(),
            remediation="Check the nexus-api pod and inference provider health.",
        )
    return Check(
        name="selva.reachable",
        status=CheckStatus.PASS,
        detail=f"HTTP {resp.status_code} from /models",
        duration_ms=dur(),
    )


async def check_deepinfra_bridge() -> Check:
    """If bridge mode is active, verify DeepInfra creds are plumbed."""
    t0 = time.perf_counter()
    key = os.environ.get("DEEPINFRA_API_KEY")
    dur = (time.perf_counter() - t0) * 1000.0
    if not key:
        return Check(
            name="bridge.deepinfra",
            status=CheckStatus.SKIP,
            detail="DEEPINFRA_API_KEY not set — bridge mode inactive",
            duration_ms=dur,
        )
    return Check(
        name="bridge.deepinfra",
        status=CheckStatus.PASS,
        detail="DEEPINFRA_API_KEY present",
        duration_ms=dur,
        facts={"mask": key[:4] + "…" + key[-2:] if len(key) > 8 else "set"},
    )


async def check_git_identity() -> Check:
    """Confirm git commit identity is configured for autonomous commits."""
    t0 = time.perf_counter()
    binary = shutil.which("git")
    dur = lambda: (time.perf_counter() - t0) * 1000.0
    if binary is None:
        return Check(
            name="git.identity",
            status=CheckStatus.SKIP,
            detail="git not on PATH (binary.git will fail too)",
            duration_ms=dur(),
        )

    async def _git(*args: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "config",
            "--get",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out.decode().strip(), err.decode().strip()

    rc_name, name, _ = await _git("user.name")
    rc_email, email, _ = await _git("user.email")

    if rc_name == 0 and rc_email == 0 and name and email:
        return Check(
            name="git.identity",
            status=CheckStatus.PASS,
            detail=f"{name} <{email}>",
            duration_ms=dur(),
            facts={"user.name": name, "user.email": email},
        )
    fallback_name = os.environ.get("GIT_AUTHOR_NAME", "autoswarm-bot")
    fallback_email = os.environ.get("GIT_AUTHOR_EMAIL", "bot@autoswarm.dev")
    return Check(
        name="git.identity",
        status=CheckStatus.WARN,
        detail="git user.name/user.email not set globally",
        duration_ms=dur(),
        remediation=(
            f"GitTool will fall back to {fallback_name} <{fallback_email}> per-repo. "
            "Set the env vars or configure globally to silence this warning."
        ),
    )


async def check_redis() -> Check:
    t0 = time.perf_counter()
    url = os.environ.get("REDIS_URL", "")
    dur = (time.perf_counter() - t0) * 1000.0
    if not url:
        return Check(
            name="redis.url",
            status=CheckStatus.FAIL,
            detail="REDIS_URL not set",
            duration_ms=dur,
            remediation="Redis backs the task queue + caches. Set REDIS_URL.",
        )
    if not url.startswith(("redis://", "rediss://")):
        return Check(
            name="redis.url",
            status=CheckStatus.WARN,
            detail=f"REDIS_URL has unusual scheme: {url[:12]}…",
            duration_ms=dur,
            remediation="Accepted schemes are 'redis://' and 'rediss://'.",
        )
    return Check(
        name="redis.url",
        status=CheckStatus.PASS,
        detail="looks valid",
        duration_ms=dur,
    )


async def check_database() -> Check:
    t0 = time.perf_counter()
    url = os.environ.get("DATABASE_URL", "")
    dur = (time.perf_counter() - t0) * 1000.0
    if not url:
        return Check(
            name="database.url",
            status=CheckStatus.FAIL,
            detail="DATABASE_URL not set",
            duration_ms=dur,
            remediation="Postgres backs the task + agent + ledger tables.",
        )
    if "insecure" in url or "change-me" in url:
        return Check(
            name="database.url",
            status=CheckStatus.WARN,
            detail="DATABASE_URL looks like a placeholder",
            duration_ms=dur,
            remediation="Replace placeholder credentials before running real work.",
        )
    return Check(
        name="database.url",
        status=CheckStatus.PASS,
        detail="set",
        duration_ms=dur,
    )


# --- Registry -------------------------------------------------------------


def default_checks() -> list[Callable[[], Awaitable[Check]]]:
    """Canonical preflight set. Extend here; don't inline elsewhere."""
    return [
        check_env_vars,
        check_database,
        check_redis,
        lambda: check_binary("git", required=True, purpose="commits, PR creation"),
        lambda: check_binary("enclii", required=True, purpose="deploy, logs, rollback"),
        lambda: check_binary("gh", required=False, purpose="PR + issue management"),
        lambda: check_binary("kubectl", required=False, purpose="fallback ops only"),
        check_selva_reachable,
        check_deepinfra_bridge,
        check_git_identity,
    ]
