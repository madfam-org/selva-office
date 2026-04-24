"""Deployment pre-flight checks — kustomize build + manifest hygiene.

Runs before an agent calls `deploy`/`argocd_sync` to surface the
deploys that would bounce off Kyverno policies or serve `:latest`
tags. Catches the common MADFAM failure modes we've seen on prod:

- un-pinned images (`newTag: latest` instead of a digest)
- containers missing `resources.requests`
- containers without an explicit `privileged: false`
- missing `imagePullSecrets` when the registry is GHCR

Fast-fail — the tool does NOT call kubectl, ArgoCD, or any cluster.
It runs `kustomize build` locally and parses the rendered YAML.
"""

from __future__ import annotations

import shlex
from typing import Any

import yaml

from ..base import BaseTool, ToolResult
from ..sandbox import ToolSandbox


class DeployPreflightTool(BaseTool):
    """Validate a Kustomize overlay before deploy/sync.

    Input:
      overlay_path: path to the overlay directory (e.g. infra/k8s/production)
      checks: optional list of check names to restrict to

    Output (via ``ToolResult.data``):
      {
        "verdict": "ready" | "blocked",
        "findings": [
          {"severity": "blocker|warn", "check": "image-digest-pinned",
           "resource": "Deployment/foo", "message": "..."},
          ...
        ],
        "resource_count": 14
      }

    Verdict is "blocked" if any finding has severity="blocker".
    """

    name = "deploy_preflight"
    description = "Kustomize build + manifest hygiene checks (digest pinning, resources, privileged, image pull secrets) before deploying."  # noqa: E501

    # All known checks. `default_checks` excludes advisory ones so tenant
    # swarms get blockers-only by default; `--checks all` runs advisory too.
    _DEFAULT_CHECKS: tuple[str, ...] = (
        "kustomize-build",
        "image-digest-pinned",
        "container-resources-requests",
        "container-privileged-false",
    )
    _ADVISORY_CHECKS: tuple[str, ...] = (
        "image-pull-secrets",
        "container-resources-limits",
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "overlay_path": {
                    "type": "string",
                    "description": "Kustomize overlay directory (contains kustomization.yaml).",
                },
                "checks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Named checks to run. Empty = all blocker-severity checks "
                        "(kustomize-build, image-digest-pinned, container-resources-requests, "
                        "container-privileged-false). Pass 'all' to also include advisory "
                        "checks (image-pull-secrets, container-resources-limits)."
                    ),
                    "default": [],
                },
                "repo_path": {"type": "string", "default": "."},
            },
            "required": ["overlay_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        overlay_path: str = kwargs.get("overlay_path", "")
        checks_input: list[str] = list(kwargs.get("checks") or [])
        repo_path: str = kwargs.get("repo_path", ".")

        if not overlay_path:
            return ToolResult(success=False, error="overlay_path is required")

        active_checks: set[str] = set(self._DEFAULT_CHECKS)
        if checks_input == ["all"]:
            active_checks.update(self._ADVISORY_CHECKS)
        elif checks_input:
            active_checks = set(checks_input)

        findings: list[dict[str, Any]] = []
        sandbox = ToolSandbox()

        # 1. kustomize build — also the smoke test that the overlay is valid.
        build = await sandbox.run_command(
            f"kustomize build {shlex.quote(overlay_path)}",
            cwd=repo_path,
            timeout=60.0,
        )
        if not build["success"]:
            findings.append(
                {
                    "severity": "blocker",
                    "check": "kustomize-build",
                    "resource": "",
                    "message": f"kustomize build failed: {build['stderr'].strip()[:300]}",
                }
            )
            return _to_result(findings, resource_count=0)

        try:
            docs = list(yaml.safe_load_all(build["stdout"]))
        except yaml.YAMLError as exc:
            findings.append(
                {
                    "severity": "blocker",
                    "check": "kustomize-build",
                    "resource": "",
                    "message": f"rendered YAML is invalid: {exc}",
                }
            )
            return _to_result(findings, resource_count=0)

        workloads = [d for d in docs if isinstance(d, dict) and d.get("kind") in _WORKLOAD_KINDS]

        for workload in workloads:
            resource_ref = _resource_ref(workload)
            for container in _iter_containers(workload):
                if "image-digest-pinned" in active_checks:
                    findings.extend(_check_digest_pinned(container, resource_ref))
                if "container-resources-requests" in active_checks:
                    findings.extend(_check_resources(container, resource_ref, "requests"))
                if "container-resources-limits" in active_checks:
                    findings.extend(
                        _check_resources(container, resource_ref, "limits", severity="warn")
                    )
                if "container-privileged-false" in active_checks:
                    findings.extend(_check_privileged(container, resource_ref))
            if "image-pull-secrets" in active_checks:
                findings.extend(_check_image_pull_secrets(workload, resource_ref))

        return _to_result(findings, resource_count=len(workloads))


# ---------- module-level helpers (testable in isolation) ----------


_WORKLOAD_KINDS = {
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Job",
    "CronJob",
    "ReplicaSet",
}


def _resource_ref(doc: dict[str, Any]) -> str:
    kind = doc.get("kind", "?")
    name = (doc.get("metadata") or {}).get("name", "?")
    return f"{kind}/{name}"


def _iter_containers(workload: dict[str, Any]):
    """Yield container dicts from a workload manifest (Deployment/CronJob/etc.)."""
    spec = workload.get("spec") or {}
    # Deployment/StatefulSet/DaemonSet/ReplicaSet/Job:
    template = spec.get("template") or {}
    # CronJob wraps jobTemplate.spec.template:
    if workload.get("kind") == "CronJob":
        template = (spec.get("jobTemplate") or {}).get("spec", {}).get("template") or {}
    pod_spec = template.get("spec") or {}
    yield from (pod_spec.get("containers") or [])


def _check_digest_pinned(container: dict[str, Any], resource: str) -> list[dict[str, Any]]:
    image = container.get("image", "")
    if not image:
        return []
    # A digest-pinned reference has "@sha256:" in it.
    if "@sha256:" in image:
        return []
    # `:latest` is always a blocker.
    if image.endswith(":latest") or ":" not in image.rsplit("/", 1)[-1]:
        return [
            {
                "severity": "blocker",
                "check": "image-digest-pinned",
                "resource": resource,
                "message": f"image '{image}' is not digest-pinned (found :latest or no tag)",
            }
        ]
    # A mutable tag (e.g. `:v1.2.3` or `:main`) is a blocker too — Kyverno
    # rejects it in production, and it defeats ArgoCD's reconciliation.
    return [
        {
            "severity": "blocker",
            "check": "image-digest-pinned",
            "resource": resource,
            "message": f"image '{image}' uses a mutable tag — pin by @sha256: digest instead",
        }
    ]


def _check_resources(
    container: dict[str, Any], resource: str, key: str, severity: str = "blocker"
) -> list[dict[str, Any]]:
    resources = container.get("resources") or {}
    block = resources.get(key)
    if isinstance(block, dict) and block:
        return []
    return [
        {
            "severity": severity,
            "check": f"container-resources-{key}",
            "resource": resource,
            "message": f"container '{container.get('name', '?')}' missing resources.{key}",
        }
    ]


def _check_privileged(container: dict[str, Any], resource: str) -> list[dict[str, Any]]:
    # Kyverno `disallow-privileged-containers` in MADFAM's policy fleet
    # requires an explicit `privileged: false`. Missing key = blocker.
    security = container.get("securityContext") or {}
    if "privileged" not in security:
        return [
            {
                "severity": "blocker",
                "check": "container-privileged-false",
                "resource": resource,
                "message": (
                    f"container '{container.get('name', '?')}' must set "
                    "securityContext.privileged: false explicitly (kyverno policy)"
                ),
            }
        ]
    if security["privileged"] is True:
        return [
            {
                "severity": "blocker",
                "check": "container-privileged-false",
                "resource": resource,
                "message": f"container '{container.get('name', '?')}' has privileged: true",
            }
        ]
    return []


def _check_image_pull_secrets(workload: dict[str, Any], resource: str) -> list[dict[str, Any]]:
    """Advisory — warn when a GHCR workload has no imagePullSecrets."""
    spec = workload.get("spec") or {}
    template = spec.get("template") or {}
    if workload.get("kind") == "CronJob":
        template = (spec.get("jobTemplate") or {}).get("spec", {}).get("template") or {}
    pod_spec = template.get("spec") or {}
    images = [(c.get("image") or "") for c in (pod_spec.get("containers") or [])]
    uses_private = any(img.startswith("ghcr.io/") for img in images)
    if uses_private and not pod_spec.get("imagePullSecrets"):
        return [
            {
                "severity": "warn",
                "check": "image-pull-secrets",
                "resource": resource,
                "message": "workload pulls from ghcr.io but has no imagePullSecrets",
            }
        ]
    return []


def _to_result(findings: list[dict[str, Any]], resource_count: int) -> ToolResult:
    blockers = [f for f in findings if f["severity"] == "blocker"]
    warns = [f for f in findings if f["severity"] == "warn"]
    verdict = "blocked" if blockers else "ready"
    return ToolResult(
        success=verdict == "ready",
        output=(
            f"{verdict}: {len(blockers)} blocker, {len(warns)} warning "
            f"across {resource_count} workload(s)"
        ),
        data={
            "verdict": verdict,
            "findings": findings,
            "resource_count": resource_count,
        },
    )
