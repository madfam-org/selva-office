"""Tests for db_lifecycle tools."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from selva_tools.builtins.db_lifecycle import (
    DbDumpToR2Tool,
    DbMaskAndCopyTool,
    DbRestoreFromR2Tool,
    DbSizeReportTool,
    get_db_lifecycle_tools,
)


class TestRegistry:
    def test_four_tools_exported(self) -> None:
        names = {t.name for t in get_db_lifecycle_tools()}
        assert names == {
            "db_dump_to_r2",
            "db_restore_from_r2",
            "db_mask_and_copy",
            "db_size_report",
        }

    def test_schemas_valid(self) -> None:
        for t in get_db_lifecycle_tools():
            s = t.parameters_schema()
            assert s["type"] == "object"


# -- Credential / identifier validation --------------------------------------


class TestDumpCredentials:
    @pytest.mark.asyncio
    async def test_missing_r2_endpoint_returns_error(self) -> None:
        with patch("selva_tools.builtins.db_lifecycle.R2_ENDPOINT", ""), patch(
            "selva_tools.builtins.db_lifecycle.R2_ACCESS_KEY_ID", "k"
        ), patch("selva_tools.builtins.db_lifecycle.R2_SECRET_ACCESS_KEY", "s"):
            r = await DbDumpToR2Tool().execute(
                database="selva_prod", bucket="backups"
            )
            assert r.success is False
            assert "R2_ENDPOINT" in (r.error or "")

    @pytest.mark.asyncio
    async def test_missing_key_returns_error(self) -> None:
        with patch(
            "selva_tools.builtins.db_lifecycle.R2_ENDPOINT", "https://x.r2"
        ), patch("selva_tools.builtins.db_lifecycle.R2_ACCESS_KEY_ID", ""), patch(
            "selva_tools.builtins.db_lifecycle.R2_SECRET_ACCESS_KEY", "s"
        ):
            r = await DbDumpToR2Tool().execute(
                database="selva_prod", bucket="backups"
            )
            assert r.success is False
            assert "R2_ACCESS_KEY_ID" in (r.error or "")


class TestIdentValidation:
    @pytest.mark.asyncio
    async def test_rejects_dangerous_db_name(self) -> None:
        with patch(
            "selva_tools.builtins.db_lifecycle.R2_ENDPOINT", "https://x.r2"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_ACCESS_KEY_ID", "k"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_SECRET_ACCESS_KEY", "s"
        ):
            r = await DbDumpToR2Tool().execute(
                database="selva; DROP TABLE x", bucket="b"
            )
            assert r.success is False
            assert "database" in (r.error or "")


# -- db_dump_to_r2 ----------------------------------------------------------


class TestDumpToR2:
    @pytest.mark.asyncio
    async def test_dump_command_contains_pipes(self) -> None:
        captured: dict = {}

        async def fake(shell_cmd, namespace="data", timeout=600):
            captured["cmd"] = shell_cmd
            captured["namespace"] = namespace
            return True, "upload: s3://backups/dumps/selva_prod-20260418T000000Z.sql.gz"

        with patch(
            "selva_tools.builtins.db_lifecycle.R2_ENDPOINT", "https://x.r2"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_ACCESS_KEY_ID", "k"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_SECRET_ACCESS_KEY", "s"
        ), patch(
            "selva_tools.builtins.db_lifecycle._exec_in_postgres", new=fake
        ):
            r = await DbDumpToR2Tool().execute(
                database="selva_prod", bucket="backups"
            )
            assert r.success is True
            assert "pg_dump" in captured["cmd"]
            assert "gzip" in captured["cmd"]
            assert "aws" in captured["cmd"]
            assert "s3://backups/" in captured["cmd"]
            assert captured["namespace"] == "data"

    @pytest.mark.asyncio
    async def test_dump_exec_failure_bubbles_up(self) -> None:
        async def fake(shell_cmd, namespace="data", timeout=600):
            return False, "no postgres pod"

        with patch(
            "selva_tools.builtins.db_lifecycle.R2_ENDPOINT", "https://x.r2"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_ACCESS_KEY_ID", "k"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_SECRET_ACCESS_KEY", "s"
        ), patch(
            "selva_tools.builtins.db_lifecycle._exec_in_postgres", new=fake
        ):
            r = await DbDumpToR2Tool().execute(
                database="selva_prod", bucket="backups"
            )
            assert r.success is False
            assert "no postgres pod" in (r.error or "")


# -- db_restore_from_r2 -----------------------------------------------------


class TestRestoreFromR2:
    @pytest.mark.asyncio
    async def test_restore_with_create_if_missing(self) -> None:
        captured: dict = {}

        async def fake(shell_cmd, namespace="data", timeout=3600):
            captured["cmd"] = shell_cmd
            return True, "COPY 1000"

        with patch(
            "selva_tools.builtins.db_lifecycle.R2_ENDPOINT", "https://x.r2"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_ACCESS_KEY_ID", "k"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_SECRET_ACCESS_KEY", "s"
        ), patch(
            "selva_tools.builtins.db_lifecycle._exec_in_postgres", new=fake
        ):
            r = await DbRestoreFromR2Tool().execute(
                bucket="backups",
                key="dumps/x.sql.gz",
                target_database="selva_staging",
                create_if_missing=True,
            )
            assert r.success is True
            assert "createdb" in captured["cmd"]
            assert "gunzip" in captured["cmd"]
            assert "psql" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_restore_without_create(self) -> None:
        captured: dict = {}

        async def fake(shell_cmd, namespace="data", timeout=3600):
            captured["cmd"] = shell_cmd
            return True, ""

        with patch(
            "selva_tools.builtins.db_lifecycle.R2_ENDPOINT", "https://x.r2"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_ACCESS_KEY_ID", "k"
        ), patch(
            "selva_tools.builtins.db_lifecycle.R2_SECRET_ACCESS_KEY", "s"
        ), patch(
            "selva_tools.builtins.db_lifecycle._exec_in_postgres", new=fake
        ):
            await DbRestoreFromR2Tool().execute(
                bucket="backups",
                key="dumps/x.sql.gz",
                target_database="selva_staging",
            )
            assert "createdb" not in captured["cmd"]


# -- db_mask_and_copy -------------------------------------------------------


class TestMaskAndCopy:
    @pytest.mark.asyncio
    async def test_mask_update_statements_generated(self) -> None:
        captured: dict = {}

        async def fake(shell_cmd, namespace="data", timeout=3600):
            captured["cmd"] = shell_cmd
            return True, "UPDATE 500"

        with patch(
            "selva_tools.builtins.db_lifecycle._exec_in_postgres", new=fake
        ):
            r = await DbMaskAndCopyTool().execute(
                source_db="selva_prod",
                target_db="selva_staging",
                table_mask_rules={
                    "users": ["email", "phone"],
                    "leads": ["contact_email"],
                },
            )
            assert r.success is True
            assert r.data["columns_masked"] == 3
            assert "users" in r.data["tables_masked"]
            assert "encode(sha256" in captured["cmd"]
            assert "pg_dump" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_empty_rules_rejected(self) -> None:
        r = await DbMaskAndCopyTool().execute(
            source_db="a", target_db="b", table_mask_rules={}
        )
        assert r.success is False

    @pytest.mark.asyncio
    async def test_bad_column_name_rejected(self) -> None:
        r = await DbMaskAndCopyTool().execute(
            source_db="a",
            target_db="b",
            table_mask_rules={"users": ["email; DROP"]},
        )
        assert r.success is False


# -- db_size_report ---------------------------------------------------------


class TestSizeReport:
    @pytest.mark.asyncio
    async def test_parses_pipe_separated_output(self) -> None:
        sample = (
            "public|users|10000|8388608\n"
            "public|tasks|5000|4194304\n"
            "public|events|250000|20971520\n"
        )

        async def fake(shell_cmd, namespace="data", timeout=120):
            return True, sample

        with patch(
            "selva_tools.builtins.db_lifecycle._exec_in_postgres", new=fake
        ):
            r = await DbSizeReportTool().execute(database="selva_prod")
            assert r.success is True
            assert r.data["table_count"] == 3
            assert r.data["total_bytes"] == 8388608 + 4194304 + 20971520
            assert r.data["tables"][2]["table"] == "events"

    @pytest.mark.asyncio
    async def test_size_report_exec_failure(self) -> None:
        async def fake(shell_cmd, namespace="data", timeout=120):
            return False, "psql: FATAL: database does not exist"

        with patch(
            "selva_tools.builtins.db_lifecycle._exec_in_postgres", new=fake
        ):
            r = await DbSizeReportTool().execute(database="nonexistent")
            assert r.success is False
            assert "does not exist" in (r.error or "")
