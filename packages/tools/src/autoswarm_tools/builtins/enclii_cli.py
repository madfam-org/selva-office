"""Shell-out tool for the ``enclii`` CLI.

Complements the HTTP Switchyard tools in :mod:`enclii_infra` by giving
agents direct access to the ``enclii`` binary for subcommands that don't
have a Switchyard API equivalent (e.g. ``enclii onboard``, ``enclii domains
add``, ``enclii junctions``).

Design:

1. **Binary must be present.** If ``enclii`` isn't on ``PATH``, this tool
   fails loudly (``/doctor`` surfaces the same condition). Worker images
   must install it at build time.
2. **Command allowlist.** Subcommands are classified into three risk
   tiers — ``readonly``, ``mutating``, ``dangerous`` — and the tool
   honours the permission matrix via the classifier in
   :mod:`autoswarm_permissions.classifier`. Agents do NOT prompt for
   readonly subcommands; mutating goes through ASK-level approval; a
   curated dangerous list is DENY unless policy overrides it.
3. **Auth.** Credentials come from ``ENCLII_API_TOKEN`` (bearer) or an
   org-level Vault binding; never from per-call arguments.
4. **Timeout.** Default 60 s. Read-only gets 30 s, long-running
   subcommands (``deploy``, ``logs -f``) get 300 s.

The tool is a thin, audit-friendly wrapper; it does not reimplement enclii
semantics — it only constrains which commands the agent can invoke and
emits structured output.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class EncliiRisk(StrEnum):
    """Per-subcommand risk tier. Maps onto the HITL permission matrix."""

    READONLY = "readonly"
    MUTATING = "mutating"
    DANGEROUS = "dangerous"


@dataclass(frozen=True)
class EncliiSubcommandPolicy:
    """Whether a subcommand is allowed, and at what risk tier."""

    name: str
    risk: EncliiRisk
    timeout_s: float = 60.0
    # Extra guard clauses applied before execution. Each callable gets the
    # full argv (minus the `enclii` itself) and returns an optional
    # rejection reason.
    preflight: tuple = ()


# Canonical subcommand classification. Extend here, never inline elsewhere.
ENCLII_POLICY: dict[str, EncliiSubcommandPolicy] = {
    # --- Readonly ------------------------------------------------------
    "ps": EncliiSubcommandPolicy("ps", EncliiRisk.READONLY, timeout_s=30.0),
    "status": EncliiSubcommandPolicy("status", EncliiRisk.READONLY, timeout_s=30.0),
    "logs": EncliiSubcommandPolicy("logs", EncliiRisk.READONLY, timeout_s=300.0),
    "builds": EncliiSubcommandPolicy("builds", EncliiRisk.READONLY, timeout_s=30.0),
    "domains": EncliiSubcommandPolicy("domains", EncliiRisk.READONLY, timeout_s=30.0),
    "junctions": EncliiSubcommandPolicy("junctions", EncliiRisk.READONLY, timeout_s=30.0),
    "jobs": EncliiSubcommandPolicy("jobs", EncliiRisk.READONLY, timeout_s=30.0),
    "env": EncliiSubcommandPolicy("env", EncliiRisk.READONLY, timeout_s=30.0),
    "whoami": EncliiSubcommandPolicy("whoami", EncliiRisk.READONLY, timeout_s=15.0),
    "help": EncliiSubcommandPolicy("help", EncliiRisk.READONLY, timeout_s=15.0),
    "version": EncliiSubcommandPolicy("version", EncliiRisk.READONLY, timeout_s=15.0),
    # --- Mutating (HITL ASK via permission matrix) ---------------------
    "deploy": EncliiSubcommandPolicy("deploy", EncliiRisk.MUTATING, timeout_s=300.0),
    "rollback": EncliiSubcommandPolicy("rollback", EncliiRisk.MUTATING, timeout_s=120.0),
    "restart": EncliiSubcommandPolicy("restart", EncliiRisk.MUTATING, timeout_s=120.0),
    "scale": EncliiSubcommandPolicy("scale", EncliiRisk.MUTATING, timeout_s=60.0),
    "onboard": EncliiSubcommandPolicy("onboard", EncliiRisk.MUTATING, timeout_s=180.0),
    "secrets": EncliiSubcommandPolicy("secrets", EncliiRisk.MUTATING, timeout_s=30.0),
    "up": EncliiSubcommandPolicy("up", EncliiRisk.MUTATING, timeout_s=300.0),
    # --- Dangerous (DENY by default — policy must explicitly allow) ----
    "destroy": EncliiSubcommandPolicy("destroy", EncliiRisk.DANGEROUS, timeout_s=120.0),
    "reset": EncliiSubcommandPolicy("reset", EncliiRisk.DANGEROUS, timeout_s=120.0),
    "nuke": EncliiSubcommandPolicy("nuke", EncliiRisk.DANGEROUS, timeout_s=120.0),
}


# Arg-level guards. Any argv containing these flags is rejected regardless
# of subcommand risk tier. Agents cannot enable them via policy escalation.
FORBIDDEN_GLOBAL_FLAGS: tuple[str, ...] = (
    "--force-delete",
    "--no-audit",
    "--skip-hooks",
)


def _find_binary() -> str | None:
    """Locate ``enclii`` on PATH, or return None if absent."""
    return shutil.which("enclii")


def _classify(argv: list[str]) -> tuple[EncliiSubcommandPolicy | None, str | None]:
    """Return (policy, rejection_reason). argv includes the subcommand as argv[0]."""
    if not argv:
        return None, "empty command"
    subcmd = argv[0].lower()
    policy = ENCLII_POLICY.get(subcmd)
    if policy is None:
        return None, f"unknown subcommand {subcmd!r} — add to ENCLII_POLICY to allow"
    for flag in FORBIDDEN_GLOBAL_FLAGS:
        if flag in argv:
            return policy, f"forbidden flag {flag!r} in argv"
    return policy, None


async def _run_subprocess(cmd: list[str], timeout_s: float, env: dict[str, str]) -> ToolResult:
    """Run the subprocess, capture stdout/stderr, enforce timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        return ToolResult(success=False, error="enclii binary not found on PATH")
    except PermissionError as exc:
        return ToolResult(success=False, error=f"enclii binary not executable: {exc}")

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return ToolResult(
            success=False,
            error=f"enclii command exceeded timeout of {timeout_s:.0f}s and was killed",
        )

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    return ToolResult(
        success=proc.returncode == 0,
        output=stdout,
        error=stderr if proc.returncode != 0 else None,
        data={
            "returncode": proc.returncode,
            "stdout_bytes": len(stdout_b),
            "stderr_bytes": len(stderr_b),
        },
    )


class EncliiCliTool(BaseTool):
    """Invoke the ``enclii`` CLI with classification + allowlist enforcement.

    Agents should prefer this over ``BashTool`` for anything enclii-shaped,
    so the audit trail carries the subcommand classification and the
    permission engine knows what tier the call is.
    """

    name = "enclii_cli"
    description = (
        "Run an allowlisted enclii subcommand (ps, logs, deploy, rollback, "
        "secrets, onboard, etc.). Readonly subcommands execute without "
        "approval; mutating ones go through the HITL matrix; dangerous "
        "ones require explicit policy override. Binary must be on PATH."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subcommand": {
                    "type": "string",
                    "description": (
                        "The enclii subcommand (first positional arg after "
                        "`enclii`), e.g. 'ps', 'logs', 'deploy'."
                    ),
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional argv after the subcommand. Each element is one argv entry.",
                    "default": [],
                },
                "timeout_s": {
                    "type": "number",
                    "description": "Optional override for the per-subcommand default timeout.",
                },
            },
            "required": ["subcommand"],
        }

    def _build_env(self) -> dict[str, str]:
        # Clean passthrough of the current env plus the bits enclii needs.
        env = os.environ.copy()
        # Enclii honours these; we surface them explicitly so a missing
        # token fails in /doctor, not mid-deploy.
        env.setdefault("ENCLII_API_URL", os.environ.get("ENCLII_API_URL", ""))
        env.setdefault("ENCLII_API_TOKEN", os.environ.get("ENCLII_API_TOKEN", ""))
        return env

    async def execute(self, **kwargs: Any) -> ToolResult:
        subcommand = str(kwargs.get("subcommand", "")).strip().lower()
        raw_args = kwargs.get("args", []) or []
        if not isinstance(raw_args, list):
            return ToolResult(success=False, error="'args' must be a list of strings")
        extra_args = [str(a) for a in raw_args]
        timeout_override = kwargs.get("timeout_s")

        argv = [subcommand, *extra_args]
        policy, reject = _classify(argv)
        if reject:
            return ToolResult(success=False, error=f"enclii policy rejected: {reject}")
        assert policy is not None  # for mypy — reject would have returned

        if policy.risk is EncliiRisk.DANGEROUS:
            # Dangerous subcommands don't run unless the calling graph
            # explicitly set `allow_dangerous_enclii=True` via a task flag.
            # The enforcement happens in the permission engine, NOT here.
            # This tool only refuses if we can observe no escalation.
            if kwargs.get("_policy_override") != "explicit":
                return ToolResult(
                    success=False,
                    error=(
                        f"enclii {subcommand} is classified DANGEROUS. "
                        "Dispatch with `allow_dangerous_enclii=true` after "
                        "human sign-off."
                    ),
                )

        binary = _find_binary()
        if binary is None:
            return ToolResult(
                success=False,
                error="enclii binary not found on PATH (run /doctor for diagnosis)",
            )

        # Sanity-check token presence for mutating / dangerous calls.
        env = self._build_env()
        if policy.risk is not EncliiRisk.READONLY and not env.get("ENCLII_API_TOKEN"):
            return ToolResult(
                success=False,
                error="ENCLII_API_TOKEN is empty — refusing to run a mutating enclii call",
            )

        cmd = [binary, *argv]
        timeout = float(timeout_override or policy.timeout_s)
        logger.info(
            "enclii_cli invoking %s (risk=%s, timeout=%.0fs)",
            shlex.join(cmd),
            policy.risk.value,
            timeout,
        )
        result = await _run_subprocess(cmd, timeout_s=timeout, env=env)
        result.data["subcommand"] = subcommand
        result.data["risk"] = policy.risk.value
        result.data["timeout_s"] = timeout
        return result
