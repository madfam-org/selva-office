"""Tests for the doctor runner + built-in checks."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from autoswarm_doctor import Check, CheckStatus, Doctor, DoctorReport
from autoswarm_doctor.checks import (
    check_binary,
    check_database,
    check_deepinfra_bridge,
    check_env_vars,
    check_git_identity,
    check_redis,
    check_selva_reachable,
)


def _fresh_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "DATABASE_URL",
        "REDIS_URL",
        "SELVA_API_BASE",
        "SELVA_API_KEY",
        "ENCLII_API_URL",
        "ENCLII_API_TOKEN",
        "DEEPINFRA_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)


async def test_env_vars_fail_when_required_missing(monkeypatch):
    _fresh_env(monkeypatch)
    c = await check_env_vars()
    assert c.status is CheckStatus.FAIL
    assert "DATABASE_URL" in c.detail or "REDIS_URL" in c.detail


async def test_env_vars_warn_when_only_recommended_missing(monkeypatch):
    _fresh_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    c = await check_env_vars()
    assert c.status is CheckStatus.WARN
    assert "SELVA_API_BASE" in (c.detail or "") or "ENCLII_API_URL" in (c.detail or "")


async def test_env_vars_pass_when_everything_set(monkeypatch):
    _fresh_env(monkeypatch)
    for k in (
        "DATABASE_URL",
        "REDIS_URL",
        "SELVA_API_BASE",
        "SELVA_API_KEY",
        "ENCLII_API_URL",
        "ENCLII_API_TOKEN",
    ):
        monkeypatch.setenv(k, "present")
    c = await check_env_vars()
    assert c.status is CheckStatus.PASS


async def test_binary_present(monkeypatch):
    with patch("autoswarm_doctor.checks.shutil.which", return_value="/usr/local/bin/git"):
        c = await check_binary("git", required=True)
    assert c.status is CheckStatus.PASS
    assert c.facts["path"] == "/usr/local/bin/git"


async def test_binary_missing_required_fails():
    with patch("autoswarm_doctor.checks.shutil.which", return_value=None):
        c = await check_binary("enclii", required=True, purpose="deploy")
    assert c.status is CheckStatus.FAIL
    assert "not on PATH" in c.detail
    assert c.remediation and "deploy" in c.remediation


async def test_binary_missing_optional_warns():
    with patch("autoswarm_doctor.checks.shutil.which", return_value=None):
        c = await check_binary("gh", required=False)
    assert c.status is CheckStatus.WARN


async def test_redis_fail_when_unset(monkeypatch):
    _fresh_env(monkeypatch)
    c = await check_redis()
    assert c.status is CheckStatus.FAIL


async def test_redis_warn_on_weird_scheme(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "memcached://whoops")
    c = await check_redis()
    assert c.status is CheckStatus.WARN


async def test_database_placeholder_warns(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:insecure@host/db")
    c = await check_database()
    assert c.status is CheckStatus.WARN


async def test_deepinfra_bridge_skip_when_unset(monkeypatch):
    _fresh_env(monkeypatch)
    c = await check_deepinfra_bridge()
    assert c.status is CheckStatus.SKIP


async def test_deepinfra_bridge_pass_when_set(monkeypatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "dikey_abcdefghij12")
    c = await check_deepinfra_bridge()
    assert c.status is CheckStatus.PASS
    # Key is masked in facts.
    assert "abcd" not in (c.facts.get("mask", "") or "")[:-2].replace("…", "")


async def test_selva_reachable_skip_when_unset(monkeypatch):
    _fresh_env(monkeypatch)
    c = await check_selva_reachable()
    assert c.status is CheckStatus.SKIP


async def test_doctor_aggregates_report(monkeypatch):
    async def _ok():
        return Check("ok1", CheckStatus.PASS, "ok")

    async def _fail():
        return Check("bad", CheckStatus.FAIL, "broken")

    async def _warn():
        return Check("warn", CheckStatus.WARN, "tense")

    doctor = Doctor(checks=[_ok, _fail, _warn])
    report = await doctor.run()
    assert isinstance(report, DoctorReport)
    assert not report.ok
    assert report.fail_count == 1
    assert report.warn_count == 1
    # JSON round-trips cleanly
    parsed = json.loads(report.to_json())
    assert parsed["fail_count"] == 1
    # Text contains the bad check and its detail
    assert "bad" in report.to_text()


async def test_doctor_catches_raising_check():
    async def _raiser():
        raise RuntimeError("boom")

    doctor = Doctor(checks=[_raiser])
    report = await doctor.run()
    assert len(report.checks) == 1
    assert report.checks[0].status is CheckStatus.FAIL
    assert "boom" in report.checks[0].detail


async def test_report_ok_true_only_when_no_fail():
    async def _warn():
        return Check("warn", CheckStatus.WARN, "meh")

    report = await Doctor(checks=[_warn]).run()
    # Warnings alone do NOT block.
    assert report.ok
    assert report.warn_count == 1


async def test_git_identity_no_git_binary_is_skip(monkeypatch):
    with patch("autoswarm_doctor.checks.shutil.which", return_value=None):
        c = await check_git_identity()
    assert c.status is CheckStatus.SKIP
