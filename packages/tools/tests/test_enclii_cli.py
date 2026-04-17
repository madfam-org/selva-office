"""Tests for EncliiCliTool.

We don't shell out to a real enclii binary here. Instead we patch the
subprocess factory and shutil.which so every test is hermetic.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoswarm_tools.builtins.enclii_cli import (
    ENCLII_POLICY,
    FORBIDDEN_GLOBAL_FLAGS,
    EncliiCliTool,
    EncliiRisk,
    _classify,
)


def test_classify_readonly():
    policy, reason = _classify(["ps"])
    assert reason is None
    assert policy is not None
    assert policy.risk is EncliiRisk.READONLY


def test_classify_mutating():
    policy, reason = _classify(["deploy", "--env", "prod"])
    assert reason is None
    assert policy is not None
    assert policy.risk is EncliiRisk.MUTATING


def test_classify_dangerous():
    policy, reason = _classify(["destroy"])
    assert reason is None
    assert policy is not None
    assert policy.risk is EncliiRisk.DANGEROUS


def test_classify_rejects_unknown_subcommand():
    policy, reason = _classify(["frobnicate"])
    assert policy is None
    assert reason is not None
    assert "unknown subcommand" in reason


def test_classify_rejects_forbidden_flag():
    policy, reason = _classify(["deploy", "--force-delete"])
    assert policy is not None  # subcommand was valid
    assert reason is not None
    assert "forbidden flag" in reason


def test_forbidden_flags_non_empty():
    # Regression: if this tuple is ever emptied by mistake, detection breaks.
    assert len(FORBIDDEN_GLOBAL_FLAGS) >= 1


def test_policy_table_covers_required_subcommands():
    required = {"ps", "logs", "deploy", "rollback", "secrets", "destroy"}
    assert required.issubset(ENCLII_POLICY.keys())


async def test_execute_rejects_empty_subcommand():
    tool = EncliiCliTool()
    result = await tool.execute(subcommand="", args=[])
    assert not result.success
    assert "unknown subcommand" in (result.error or "")


async def test_execute_rejects_bad_args_type():
    tool = EncliiCliTool()
    result = await tool.execute(subcommand="ps", args="not-a-list")  # type: ignore[arg-type]
    assert not result.success
    assert "must be a list" in (result.error or "")


async def test_execute_rejects_dangerous_without_override(monkeypatch):
    monkeypatch.setenv("ENCLII_API_TOKEN", "t")
    with patch("autoswarm_tools.builtins.enclii_cli.shutil.which", return_value="/usr/local/bin/enclii"):
        tool = EncliiCliTool()
        result = await tool.execute(subcommand="destroy", args=[])
    assert not result.success
    assert "DANGEROUS" in (result.error or "")


async def test_execute_reports_missing_binary(monkeypatch):
    monkeypatch.setenv("ENCLII_API_TOKEN", "t")
    with patch("autoswarm_tools.builtins.enclii_cli.shutil.which", return_value=None):
        tool = EncliiCliTool()
        result = await tool.execute(subcommand="ps", args=[])
    assert not result.success
    assert "binary not found" in (result.error or "")


async def test_execute_reports_missing_token_for_mutating(monkeypatch):
    monkeypatch.delenv("ENCLII_API_TOKEN", raising=False)
    with patch("autoswarm_tools.builtins.enclii_cli.shutil.which", return_value="/usr/local/bin/enclii"):
        tool = EncliiCliTool()
        result = await tool.execute(subcommand="deploy", args=["--env", "prod"])
    assert not result.success
    assert "ENCLII_API_TOKEN" in (result.error or "")


async def test_execute_readonly_runs_without_token(monkeypatch):
    """ps / logs / status should not require a token — local-only info."""
    monkeypatch.delenv("ENCLII_API_TOKEN", raising=False)

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.communicate = AsyncMock(return_value=(b"enclii v1.2.3\n", b""))

    async def fake_exec(*args, **kwargs):
        return fake_proc

    with patch("autoswarm_tools.builtins.enclii_cli.shutil.which", return_value="/usr/local/bin/enclii"), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        tool = EncliiCliTool()
        result = await tool.execute(subcommand="version", args=[])

    assert result.success
    assert "enclii v1.2.3" in result.output
    assert result.data["subcommand"] == "version"
    assert result.data["risk"] == "readonly"
    assert result.data["returncode"] == 0


async def test_execute_mutating_surfaces_non_zero_rc(monkeypatch):
    monkeypatch.setenv("ENCLII_API_TOKEN", "t")

    fake_proc = MagicMock()
    fake_proc.returncode = 42
    fake_proc.communicate = AsyncMock(return_value=(b"", b"permission denied\n"))

    async def fake_exec(*args, **kwargs):
        return fake_proc

    with patch("autoswarm_tools.builtins.enclii_cli.shutil.which", return_value="/usr/local/bin/enclii"), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        tool = EncliiCliTool()
        result = await tool.execute(subcommand="deploy", args=["--env", "prod"])

    assert not result.success
    assert "permission denied" in (result.error or "")
    assert result.data["returncode"] == 42
    assert result.data["risk"] == "mutating"


async def test_execute_timeout_kills_process(monkeypatch):
    monkeypatch.setenv("ENCLII_API_TOKEN", "t")

    fake_proc = MagicMock()
    fake_proc.returncode = -9
    fake_proc.kill = MagicMock()
    fake_proc.wait = AsyncMock()
    # communicate() never returns in time
    never_completes = asyncio.get_event_loop().create_future()
    fake_proc.communicate = AsyncMock(return_value=never_completes)
    fake_proc.communicate.side_effect = asyncio.TimeoutError()

    async def fake_exec(*args, **kwargs):
        return fake_proc

    with patch("autoswarm_tools.builtins.enclii_cli.shutil.which", return_value="/usr/local/bin/enclii"), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        tool = EncliiCliTool()
        # Pass very small override to keep the test fast — even without
        # the override, the timeout would fire because we mocked it to.
        result = await tool.execute(subcommand="logs", args=["my-svc"], timeout_s=0.01)

    assert not result.success
    assert "timeout" in (result.error or "").lower()


async def test_to_openai_spec_shape():
    tool = EncliiCliTool()
    spec = tool.to_openai_spec()
    assert spec["function"]["name"] == "enclii_cli"
    assert "subcommand" in spec["function"]["parameters"]["properties"]
    assert spec["function"]["parameters"]["required"] == ["subcommand"]
