"""Tests for kustomize + backup_ops tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml

from selva_tools.builtins.backup_ops import (
    PgbackrestBackupTool,
    PgbackrestCheckTool,
    PgbackrestInfoTool,
    get_backup_tools,
)
from selva_tools.builtins.kustomize import (
    KustomizeListImagesTool,
    KustomizeSetImageTool,
    get_kustomize_tools,
)


# -- Kustomize --------------------------------------------------------------


class TestKustomizeRegistry:
    def test_three_tools(self) -> None:
        names = {t.name for t in get_kustomize_tools()}
        assert names == {
            "kustomize_list_images",
            "kustomize_set_image",
            "kustomize_build",
        }


class TestKustomizeListImages:
    @pytest.mark.asyncio
    async def test_reads_images_block(self, tmp_path) -> None:
        ku = tmp_path / "kustomization.yaml"
        ku.write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "kustomize.config.k8s.io/v1beta1",
                    "kind": "Kustomization",
                    "images": [
                        {
                            "name": "ghcr.io/madfam-org/madlab-client",
                            "newName": "ghcr.io/madfam-org/madlab-client",
                            "digest": "sha256:abc",
                        }
                    ],
                }
            )
        )
        r = await KustomizeListImagesTool().execute(kustomization_path=str(ku))
        assert r.success is True
        assert r.data["images"][0]["digest"] == "sha256:abc"

    @pytest.mark.asyncio
    async def test_missing_file_error(self) -> None:
        r = await KustomizeListImagesTool().execute(
            kustomization_path="/nonexistent/kustomization.yaml"
        )
        assert r.success is False
        assert "file not found" in (r.error or "")


class TestKustomizeSetImage:
    @pytest.mark.asyncio
    async def test_digest_replaces_existing_tag(self, tmp_path) -> None:
        ku = tmp_path / "kustomization.yaml"
        ku.write_text(
            yaml.safe_dump(
                {
                    "images": [
                        {
                            "name": "ghcr.io/madfam-org/madlab-client",
                            "newName": "ghcr.io/madfam-org/madlab-client",
                            "newTag": "latest",
                        }
                    ]
                }
            )
        )
        r = await KustomizeSetImageTool().execute(
            kustomization_path=str(ku),
            name="ghcr.io/madfam-org/madlab-client",
            digest="sha256:abc123",
        )
        assert r.success is True
        after = yaml.safe_load(ku.read_text())
        entry = after["images"][0]
        assert entry["digest"] == "sha256:abc123"
        assert "newTag" not in entry

    @pytest.mark.asyncio
    async def test_new_image_appended(self, tmp_path) -> None:
        ku = tmp_path / "kustomization.yaml"
        ku.write_text(yaml.safe_dump({"images": []}))
        r = await KustomizeSetImageTool().execute(
            kustomization_path=str(ku),
            name="ghcr.io/madfam-org/new-service",
            digest="sha256:deadbeef",
        )
        assert r.success is True
        after = yaml.safe_load(ku.read_text())
        assert len(after["images"]) == 1
        assert after["images"][0]["digest"] == "sha256:deadbeef"

    @pytest.mark.asyncio
    async def test_neither_digest_nor_tag_errors(self, tmp_path) -> None:
        ku = tmp_path / "kustomization.yaml"
        ku.write_text(yaml.safe_dump({"images": []}))
        r = await KustomizeSetImageTool().execute(
            kustomization_path=str(ku),
            name="x",
        )
        assert r.success is False
        assert "digest" in (r.error or "")


# -- Backup ops -------------------------------------------------------------


class TestBackupRegistry:
    def test_three_tools(self) -> None:
        names = {t.name for t in get_backup_tools()}
        assert names == {
            "pgbackrest_info",
            "pgbackrest_backup",
            "pgbackrest_check",
        }


class TestBackupCheck:
    @pytest.mark.asyncio
    async def test_check_success_returns_healthy_true(self) -> None:
        with patch(
            "selva_tools.builtins.backup_ops._exec_in_pgbackrest",
            new=AsyncMock(return_value=(True, "P00   INFO: check command begin")),
        ):
            r = await PgbackrestCheckTool().execute()
            assert r.success is True
            assert r.data["healthy"] is True

    @pytest.mark.asyncio
    async def test_check_failure_returns_healthy_false(self) -> None:
        with patch(
            "selva_tools.builtins.backup_ops._exec_in_pgbackrest",
            new=AsyncMock(return_value=(False, "ERROR: stanza main does not exist")),
        ):
            r = await PgbackrestCheckTool().execute()
            assert r.success is False
            assert r.data["healthy"] is False


class TestBackupTrigger:
    @pytest.mark.asyncio
    async def test_diff_is_default(self) -> None:
        captured: dict = {}

        async def fake(cmd, namespace="data", timeout=120):
            captured["cmd"] = cmd
            return True, "backup complete"

        with patch("selva_tools.builtins.backup_ops._exec_in_pgbackrest", new=fake):
            r = await PgbackrestBackupTool().execute()
            assert r.success is True
            assert "--type" in captured["cmd"]
            assert "diff" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_full_override(self) -> None:
        captured: dict = {}

        async def fake(cmd, namespace="data", timeout=120):
            captured["cmd"] = cmd
            return True, ""

        with patch("selva_tools.builtins.backup_ops._exec_in_pgbackrest", new=fake):
            await PgbackrestBackupTool().execute(type="full")
            assert "full" in captured["cmd"]


class TestBackupInfo:
    @pytest.mark.asyncio
    async def test_parses_json_output(self) -> None:
        sample = """[{"name":"main","db":[{"id":1}],"backup":[{"label":"20260418-0200F"},{"label":"20260418-0800D"}]}]"""
        with patch(
            "selva_tools.builtins.backup_ops._exec_in_pgbackrest",
            new=AsyncMock(return_value=(True, sample)),
        ):
            r = await PgbackrestInfoTool().execute()
            assert r.success is True
            assert "backup_count=2" in r.output
