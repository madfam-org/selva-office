"""Tests for DeployPreflightTool."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import yaml

# ---------- pure helper tests ----------


class TestCheckers:
    def test_digest_pinned_image_passes(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_digest_pinned

        c = {"image": "ghcr.io/x/y@sha256:abc"}
        assert _check_digest_pinned(c, "Deployment/foo") == []

    def test_latest_tag_is_blocker(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_digest_pinned

        c = {"image": "nginx:latest"}
        findings = _check_digest_pinned(c, "Deployment/foo")
        assert len(findings) == 1
        assert findings[0]["severity"] == "blocker"

    def test_mutable_tag_is_blocker(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_digest_pinned

        c = {"image": "ghcr.io/x/y:v1.2.3"}
        findings = _check_digest_pinned(c, "Deployment/foo")
        assert len(findings) == 1
        assert "mutable tag" in findings[0]["message"]

    def test_no_tag_is_blocker(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_digest_pinned

        c = {"image": "nginx"}
        findings = _check_digest_pinned(c, "Deployment/foo")
        assert len(findings) == 1

    def test_missing_resources_requests_is_blocker(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_resources

        c = {"name": "api", "resources": {"limits": {"memory": "1Gi"}}}
        findings = _check_resources(c, "Deployment/foo", "requests")
        assert len(findings) == 1
        assert findings[0]["severity"] == "blocker"

    def test_resources_requests_present_passes(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_resources

        c = {"name": "api", "resources": {"requests": {"cpu": "100m"}}}
        findings = _check_resources(c, "Deployment/foo", "requests")
        assert findings == []

    def test_privileged_missing_is_blocker(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_privileged

        findings = _check_privileged({"name": "api"}, "Deployment/foo")
        assert len(findings) == 1
        assert findings[0]["severity"] == "blocker"

    def test_privileged_false_passes(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_privileged

        c = {"name": "api", "securityContext": {"privileged": False}}
        assert _check_privileged(c, "Deployment/foo") == []

    def test_privileged_true_is_blocker(self) -> None:
        from selva_tools.builtins.deploy_preflight import _check_privileged

        c = {"name": "api", "securityContext": {"privileged": True}}
        findings = _check_privileged(c, "Deployment/foo")
        assert len(findings) == 1


# ---------- end-to-end tool tests ----------


class TestDeployPreflightTool:
    def test_schema_requires_overlay_path(self) -> None:
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        schema = DeployPreflightTool().parameters_schema()
        assert "overlay_path" in schema["required"]

    @pytest.mark.asyncio
    async def test_kustomize_build_failure_is_blocker(self, tmp_path) -> None:
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        async def run(self, command, *, timeout=30.0, cwd=None):
            return {
                "stdout": "",
                "stderr": "Error: resource not found",
                "return_code": 1,
                "success": False,
            }

        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await DeployPreflightTool().execute(
                overlay_path=str(tmp_path), repo_path=str(tmp_path)
            )

        assert not result.success
        assert result.data["verdict"] == "blocked"
        assert result.data["findings"][0]["check"] == "kustomize-build"

    @pytest.mark.asyncio
    async def test_all_checks_pass_returns_ready(self, tmp_path) -> None:
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        rendered = yaml.dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "api"},
                "spec": {
                    "template": {
                        "spec": {
                            "imagePullSecrets": [{"name": "ghcr-creds"}],
                            "containers": [
                                {
                                    "name": "api",
                                    "image": "ghcr.io/madfam/api@sha256:abc123",
                                    "resources": {
                                        "requests": {"cpu": "100m", "memory": "128Mi"},
                                        "limits": {"cpu": "1000m", "memory": "1Gi"},
                                    },
                                    "securityContext": {"privileged": False},
                                }
                            ],
                        },
                    },
                },
            }
        )

        async def run(self, command, *, timeout=30.0, cwd=None):
            return {
                "stdout": rendered,
                "stderr": "",
                "return_code": 0,
                "success": True,
            }

        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await DeployPreflightTool().execute(
                overlay_path="infra/k8s/production",
                repo_path=str(tmp_path),
            )

        assert result.success
        assert result.data["verdict"] == "ready"
        assert result.data["resource_count"] == 1

    @pytest.mark.asyncio
    async def test_aggregates_multiple_blockers(self, tmp_path) -> None:
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        # Bad: :latest tag AND no resource requests AND no privileged field.
        rendered = yaml.dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "bad"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "bad",
                                    "image": "nginx:latest",
                                }
                            ],
                        },
                    },
                },
            }
        )

        async def run(self, command, *, timeout=30.0, cwd=None):
            return {
                "stdout": rendered,
                "stderr": "",
                "return_code": 0,
                "success": True,
            }

        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await DeployPreflightTool().execute(
                overlay_path="infra/k8s/production",
                repo_path=str(tmp_path),
            )

        assert not result.success
        assert result.data["verdict"] == "blocked"
        checks = {f["check"] for f in result.data["findings"]}
        assert "image-digest-pinned" in checks
        assert "container-resources-requests" in checks
        assert "container-privileged-false" in checks

    @pytest.mark.asyncio
    async def test_cronjob_containers_are_also_checked(self, tmp_path) -> None:
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        rendered = yaml.dump(
            {
                "apiVersion": "batch/v1",
                "kind": "CronJob",
                "metadata": {"name": "nightly"},
                "spec": {
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "job",
                                            "image": "nginx:latest",  # bad
                                        }
                                    ],
                                },
                            },
                        },
                    },
                },
            }
        )

        async def run(self, command, *, timeout=30.0, cwd=None):
            return {
                "stdout": rendered,
                "stderr": "",
                "return_code": 0,
                "success": True,
            }

        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await DeployPreflightTool().execute(
                overlay_path="infra/k8s/production",
                repo_path=str(tmp_path),
            )

        assert result.data["verdict"] == "blocked"
        # At least one finding should reference the CronJob, not be empty.
        assert any(f["resource"] == "CronJob/nightly" for f in result.data["findings"])

    @pytest.mark.asyncio
    async def test_advisory_checks_opt_in_with_all(self, tmp_path) -> None:
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        # Good image, but missing limits and imagePullSecrets (both advisory).
        rendered = yaml.dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "api"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "api",
                                    "image": "ghcr.io/madfam/api@sha256:abc",
                                    "resources": {
                                        "requests": {"cpu": "100m", "memory": "128Mi"},
                                    },
                                    "securityContext": {"privileged": False},
                                }
                            ],
                        },
                    },
                },
            }
        )

        async def run(self, command, *, timeout=30.0, cwd=None):
            return {
                "stdout": rendered,
                "stderr": "",
                "return_code": 0,
                "success": True,
            }

        # Default run: blockers-only → no findings.
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result_default = await DeployPreflightTool().execute(
                overlay_path="infra/k8s/production",
                repo_path=str(tmp_path),
            )
        assert result_default.success
        assert result_default.data["findings"] == []

        # With checks=['all']: advisories surface as warnings but verdict stays ready.
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result_all = await DeployPreflightTool().execute(
                overlay_path="infra/k8s/production",
                repo_path=str(tmp_path),
                checks=["all"],
            )
        assert result_all.data["verdict"] == "ready"  # warn-only → still ready
        warns = [f for f in result_all.data["findings"] if f["severity"] == "warn"]
        assert len(warns) >= 1

    @pytest.mark.asyncio
    async def test_explicit_checks_subset_skips_unlisted_checks(self, tmp_path) -> None:
        """Passing `checks=["image-digest-pinned"]` should run ONLY that check
        — not the default four. A manifest that would be blocked by
        `container-privileged-false` must come back ready."""
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        # `privileged` is missing, image is bad — but only digest-pin runs.
        rendered = yaml.dump(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "api"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "api",
                                    "image": "nginx:latest",
                                }
                            ],
                        },
                    },
                },
            }
        )

        async def run(self, command, *, timeout=30.0, cwd=None):
            return {
                "stdout": rendered,
                "stderr": "",
                "return_code": 0,
                "success": True,
            }

        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await DeployPreflightTool().execute(
                overlay_path="infra/k8s/production",
                repo_path=str(tmp_path),
                checks=["image-digest-pinned"],
            )

        # Only the requested check ran — digest-pin blocker fires, others don't.
        checks = {f["check"] for f in result.data["findings"]}
        assert checks == {"image-digest-pinned"}

    @pytest.mark.asyncio
    async def test_non_workload_docs_are_skipped(self, tmp_path) -> None:
        """Rendered kustomize output often interleaves Services, ConfigMaps,
        ServiceAccounts with workloads. The preflight walker must only
        inspect workloads (Deployment/StatefulSet/etc.) and ignore the rest,
        or it will false-positive on every Service (which has no containers)."""
        from selva_tools.builtins.deploy_preflight import DeployPreflightTool

        rendered_parts = [
            yaml.dump(
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api"},
                    "spec": {"ports": [{"port": 80}]},
                }
            ),
            yaml.dump(
                {
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {"name": "cfg"},
                    "data": {"FOO": "bar"},
                }
            ),
            yaml.dump(
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api"},
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "name": "api",
                                        "image": "ghcr.io/madfam/api@sha256:abc",
                                        "resources": {
                                            "requests": {"cpu": "100m", "memory": "64Mi"}
                                        },
                                        "securityContext": {"privileged": False},
                                    }
                                ],
                            },
                        },
                    },
                }
            ),
        ]
        rendered = "---\n".join(rendered_parts)

        async def run(self, command, *, timeout=30.0, cwd=None):
            return {
                "stdout": rendered,
                "stderr": "",
                "return_code": 0,
                "success": True,
            }

        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await DeployPreflightTool().execute(
                overlay_path="infra/k8s/production",
                repo_path=str(tmp_path),
            )

        # Only the Deployment should count toward resource_count; Service +
        # ConfigMap are skipped. All checks pass → verdict ready.
        assert result.data["resource_count"] == 1
        assert result.data["verdict"] == "ready"
        assert result.data["findings"] == []
