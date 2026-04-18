"""Factory Manifest tools — publish + verify + read a repo's manifest.

Phase 4 of the SELVA_TOOL_COVERAGE_PLAN. The ``madfam-factory-manifest``
shared package (``packages/factory-manifest/``) is the canonical place
where each repo in the ecosystem declares its build shape (build command,
test command, language, runtime flags, deploy target, service identity).
When a repo ships a factory manifest the swarm can reason about how to
build/deploy/test it without repo-specific hand-tuning.

**Integration strategy:** We wrap the shared package via lazy import.
When the package exposes a ``publish`` / ``verify`` / ``read`` surface
(Phase 1 spike) we'll use it directly. Until then (the package is
scaffolded but the Python API is still empty), these tools fall back to
a direct filesystem read/write of ``<repo>/.factory/manifest.json``
using the `routecraft` convention — the Factory Manifest spec is
JSON-at-a-well-known-path. Publishing *also* emits a PR via
``github_admin`` when ``open_pr=true``; unless that flag is set the
write lands on the local working tree only.

All writes are diff-safe: ``factory_manifest_publish`` reads the current
manifest (if any), merges the proposed delta, and writes back only when
something actually changed. Verification returns structured errors the
agent can feed to a fix loop.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


MANIFEST_RELPATH = ".factory/manifest.json"
REQUIRED_KEYS = ("name", "version", "build", "test")


def _repo_root() -> Path:
    """Base path for repo lookups. Env ``WORKSPACES_ROOT`` overrides."""
    return Path(os.environ.get("WORKSPACES_ROOT", os.path.expanduser("~/labspace")))


def _manifest_path(repo: str) -> Path:
    # Reject path traversal. Repo arg is a bare directory name.
    if "/" in repo or ".." in repo or repo.startswith("."):
        raise ValueError(f"invalid repo name: {repo!r}")
    return _repo_root() / repo / MANIFEST_RELPATH


def _validate(manifest: dict[str, Any]) -> list[str]:
    """Return a list of validation errors. Empty list means valid."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    for key in REQUIRED_KEYS:
        if key not in manifest:
            errors.append(f"missing required key: {key!r}")
    name = manifest.get("name")
    if name is not None and not (
        isinstance(name, str) and 1 <= len(name) <= 128
    ):
        errors.append("name must be a non-empty string under 128 chars")
    version = manifest.get("version")
    if version is not None and not isinstance(version, str):
        errors.append("version must be a string (semver recommended)")
    for cmd_key in ("build", "test"):
        cmd = manifest.get(cmd_key)
        if cmd is not None and not (isinstance(cmd, str) and cmd.strip()):
            errors.append(f"{cmd_key} must be a non-empty shell command string")
    # Optional: language enumeration
    lang = manifest.get("language")
    if lang is not None and lang not in (
        "python",
        "typescript",
        "javascript",
        "go",
        "rust",
        "mixed",
        "other",
    ):
        errors.append(
            f"language {lang!r} not in python|typescript|javascript|go|rust|mixed|other"
        )
    return errors


class FactoryManifestGetForRepoTool(BaseTool):
    """Read and parse a repo's factory manifest, if any."""

    name = "factory_manifest_get_for_repo"
    description = (
        "Read the factory manifest at ``<repo>/.factory/manifest.json``. "
        "Returns the parsed manifest dict, or ``manifest=None`` when the "
        "file does not exist (this is NOT an error — most repos have not "
        "adopted the manifest yet). Also runs the schema validator and "
        "returns any validation errors in ``errors``."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
            },
            "required": ["repo"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            repo = str(kwargs["repo"])
            try:
                path = _manifest_path(repo)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))
            if not path.exists():
                return ToolResult(
                    success=True,
                    output=f"no manifest at {path}",
                    data={
                        "repo": repo,
                        "manifest": None,
                        "path": str(path),
                        "errors": [],
                    },
                )
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                return ToolResult(
                    success=False,
                    error=f"invalid JSON at {path}: {e}",
                )
            errors = _validate(manifest)
            return ToolResult(
                success=True,
                output=f"read manifest from {path}; {len(errors)} validation errors",
                data={
                    "repo": repo,
                    "manifest": manifest,
                    "path": str(path),
                    "errors": errors,
                },
            )
        except Exception as e:
            logger.error("factory_manifest_get_for_repo failed: %s", e)
            return ToolResult(success=False, error=str(e))


class FactoryManifestVerifyTool(BaseTool):
    """Verify an existing repo manifest against the factory-manifest schema."""

    name = "factory_manifest_verify"
    description = (
        "Validate a repo's factory manifest. Returns ``valid=True/False`` "
        "plus a structured ``errors`` list (one string per problem). A "
        "missing manifest file is reported as ``valid=False`` with a "
        "single 'manifest file not found' error — the verify tool is "
        "opinionated: repos SHOULD have a manifest."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
            },
            "required": ["repo"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            repo = str(kwargs["repo"])
            try:
                path = _manifest_path(repo)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))
            if not path.exists():
                return ToolResult(
                    success=True,
                    output=f"manifest missing at {path}",
                    data={
                        "repo": repo,
                        "valid": False,
                        "errors": ["manifest file not found"],
                        "path": str(path),
                    },
                )
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                return ToolResult(
                    success=True,
                    output=f"manifest JSON invalid",
                    data={
                        "repo": repo,
                        "valid": False,
                        "errors": [f"invalid JSON: {e}"],
                        "path": str(path),
                    },
                )
            errors = _validate(manifest)
            return ToolResult(
                success=True,
                output=f"valid={not errors} ({len(errors)} errors)",
                data={
                    "repo": repo,
                    "valid": not errors,
                    "errors": errors,
                    "path": str(path),
                },
            )
        except Exception as e:
            logger.error("factory_manifest_verify failed: %s", e)
            return ToolResult(success=False, error=str(e))


class FactoryManifestPublishTool(BaseTool):
    """Write / merge a factory manifest into a repo (local working tree)."""

    name = "factory_manifest_publish"
    description = (
        "Write a factory manifest into ``<repo>/.factory/manifest.json``. "
        "When an existing manifest is present, the incoming ``manifest`` "
        "argument is MERGED on top (top-level key overwrite; no deep merge). "
        "Writes nothing when the effective manifest is unchanged. Always "
        "runs the schema validator first — refuses to write when "
        "validation fails. Returns the PR URL only when ``open_pr=true`` "
        "and a ``github_admin`` equivalent is actually hooked up; today "
        "we surface the manifest_path so a composing skill can hand off "
        "to github_admin in a follow-up call."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "manifest": {"type": "object"},
                "open_pr": {"type": "boolean", "default": False},
                "commit_message": {"type": "string"},
            },
            "required": ["repo", "manifest"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            repo = str(kwargs["repo"])
            incoming = kwargs.get("manifest")
            if not isinstance(incoming, dict):
                return ToolResult(
                    success=False,
                    error="manifest argument must be an object",
                )
            try:
                path = _manifest_path(repo)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))
            repo_dir = _repo_root() / repo
            if not repo_dir.exists():
                return ToolResult(
                    success=False,
                    error=f"repo directory not found: {repo_dir}",
                )
            # Merge with existing if any.
            current: dict[str, Any] = {}
            if path.exists():
                try:
                    current = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(current, dict):
                        current = {}
                except json.JSONDecodeError:
                    current = {}
            merged = {**current, **incoming}
            errors = _validate(merged)
            if errors:
                return ToolResult(
                    success=False,
                    error=f"manifest fails validation: {'; '.join(errors)}",
                )
            if merged == current:
                return ToolResult(
                    success=True,
                    output=f"no change — manifest already matches",
                    data={
                        "repo": repo,
                        "path": str(path),
                        "changed": False,
                        "pr_url": None,
                    },
                )
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(merged, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=f"could not write manifest: {e}",
                )
            pr_url: str | None = None
            if bool(kwargs.get("open_pr")):
                # We don't invoke github_admin here — that lives in the
                # skill layer. Instead we signal the caller via a dedicated
                # field so the skill knows to chain a github_admin call.
                pr_url = "pending: caller must chain github_admin_create_pr"
            return ToolResult(
                success=True,
                output=f"wrote manifest to {path}",
                data={
                    "repo": repo,
                    "path": str(path),
                    "changed": True,
                    "manifest": merged,
                    "pr_url": pr_url,
                    "commit_message": kwargs.get(
                        "commit_message",
                        f"chore(factory): publish manifest for {repo}",
                    ),
                },
            )
        except Exception as e:
            logger.error("factory_manifest_publish failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_factory_manifest_tools() -> list[BaseTool]:
    """Return the factory-manifest tool set."""
    return [
        FactoryManifestGetForRepoTool(),
        FactoryManifestVerifyTool(),
        FactoryManifestPublishTool(),
    ]


# ``subprocess`` is imported for future git hooks (e.g. staging the file
# via ``git add`` before a PR is opened). Currently unused but kept to
# avoid churn when the skill-level composition is wired.
_ = subprocess
