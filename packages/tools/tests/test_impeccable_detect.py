"""impeccable_detect: allowlist, pinned binary, telemetry-off env, findings shape."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from selva_tools.builtins import impeccable_detect as mod
from selva_tools.builtins.impeccable_detect import ImpeccableDetectTool

ENGINE = mod.load_pin()["engine_version"] if mod.load_pin() else "missing"

_FINDINGS = [
    {
        "antipattern": "overused-font",
        "name": "Overused font",
        "description": "Inter is everywhere.",
        "severity": "warning",
        "category": "slop",
        "file": "{repo}/web/globals.css",
        "line": 3,
        "snippet": "font-family: 'Inter",
    },
    {
        "antipattern": "em-dash-overuse",
        "name": "Em dash overuse",
        "severity": "advisory",
        "category": "quality",
        "file": "web/page.tsx",
        "line": 9,
        "snippet": "-- -- --",
        "advisory": True,
    },
]


def _fake_engine(tmp_path: Path, *, version: str = "", findings: list | None = None) -> Path:
    """A stand-in engine: records argv + env, prints --version or JSON findings."""
    record = tmp_path / "record"
    record.mkdir()
    payload = json.dumps(findings if findings is not None else _FINDINGS)
    script = tmp_path / "impeccable"
    script.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "{version or ENGINE + "+engine"}"; exit 0; fi\n'
        f'printf "%s\\n" "$@" > "{record}/argv"\n'
        f'env > "{record}/env"\n'
        f"cat <<'JSON' | sed \"s#{{repo}}#$PWD#\"\n{payload}\nJSON\n"
        f"exit {2 if (findings is None or findings) else 0}\n"
    )
    script.chmod(0o755)
    return script


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "web").mkdir(parents=True)
    (root / "web" / "globals.css").write_text("body { font-family: 'Inter'; }\n")
    (root / "web" / "page.tsx").write_text("export const P = () => <h1>Hi</h1>;\n")
    (root / "api.py").write_text("x = 1\n")
    return root


# -- allowlist -----------------------------------------------------------------------


def test_registered_as_tenant_builtin() -> None:
    from selva_tools.audience import Audience
    from selva_tools.builtins import get_builtin_tools

    tools = {t.name: t for t in get_builtin_tools()}
    assert isinstance(tools["impeccable_detect"], ImpeccableDetectTool)
    assert tools["impeccable_detect"].audience is Audience.TENANT


def test_policy_is_read_only_and_allowed_unattended() -> None:
    from selva_permissions.engine import PermissionEngine
    from selva_permissions.tool_policy import BUILTIN_TOOL_POLICY, SideEffect
    from selva_permissions.types import ActionCategory, PermissionLevel

    policy = BUILTIN_TOOL_POLICY["impeccable_detect"]
    assert policy.side_effect is SideEffect.READ_ONLY
    assert policy.category is ActionCategory.FILE_READ
    assert PermissionEngine().evaluate(policy.category).level is PermissionLevel.ALLOW


def test_ui_extensions_match_the_skill_package() -> None:
    from selva_skills.impeccable import UI_FILE_EXTENSIONS

    assert mod.UI_FILE_EXTENSIONS == UI_FILE_EXTENSIONS


# -- environment ---------------------------------------------------------------------


def test_detector_env_forces_telemetry_off_and_drops_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-test-not-real")
    monkeypatch.setenv("DO_NOT_TRACK", "0")  # an opt-in attempt must not survive
    env = mod.detector_env()
    assert env["IMPECCABLE_NO_TELEMETRY"] == "1"
    assert env["DO_NOT_TRACK"] == "1"
    assert "ANTHROPIC_API_KEY" not in env and "GITHUB_TOKEN" not in env
    assert set(env) <= {*mod._INHERITED_ENV, *mod.TELEMETRY_OFF_ENV}


# -- execution -------------------------------------------------------------------------


async def test_runs_pinned_binary_read_only_with_telemetry_off(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _fake_engine(tmp_path)
    monkeypatch.setenv("IMPECCABLE_BIN", str(engine))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")

    result = await ImpeccableDetectTool().execute(
        repo_path=str(repo), paths=["web/globals.css", "web/page.tsx"]
    )

    argv = (tmp_path / "record" / "argv").read_text().split()
    assert argv == ["detect", "--json", "web/globals.css", "web/page.tsx"]
    env = (tmp_path / "record" / "env").read_text()
    assert "IMPECCABLE_NO_TELEMETRY=1" in env and "DO_NOT_TRACK=1" in env
    assert "OPENAI_API_KEY" not in env

    assert result.success is False  # primary findings remain
    data = result.data
    assert data["status"] == "findings"
    assert data["telemetry"] == "off"
    assert data["engine_version"] == ENGINE
    assert (data["primary_count"], data["advisory_count"]) == (1, 1)
    first = data["findings"][0]
    assert first["rule"] == "overused-font"
    assert first["file"] == "web/globals.css"  # absolute path made repo-relative
    assert first["advisory"] is False
    assert data["findings"][1]["advisory"] is True


async def test_clean_scan_succeeds(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPECCABLE_BIN", str(_fake_engine(tmp_path, findings=[])))
    result = await ImpeccableDetectTool().execute(repo_path=str(repo), paths=["web/page.tsx"])
    assert result.success is True
    assert result.data["status"] == "clean"


async def test_scope_is_passed_through(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPECCABLE_BIN", str(_fake_engine(tmp_path)))
    await ImpeccableDetectTool().execute(
        repo_path=str(repo), paths=["web/page.tsx"], scope=["layout", "bogus", "type"]
    )
    argv = (tmp_path / "record" / "argv").read_text().split()
    assert argv == ["detect", "--json", "--scope", "layout,type", "web/page.tsx"]


async def test_version_mismatch_is_refused(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPECCABLE_BIN", str(_fake_engine(tmp_path, version="0.0.1+engine")))
    result = await ImpeccableDetectTool().execute(repo_path=str(repo), paths=["web/page.tsx"])
    assert result.success is False
    assert result.data["status"] == "unavailable"
    assert "pinned engine" in (result.error or "")
    assert not (tmp_path / "record" / "argv").exists()


async def test_missing_binary_fails_visible(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPECCABLE_BIN", str(tmp_path / "nope"))
    monkeypatch.setattr(mod, "DEFAULT_BIN", str(tmp_path / "nope-either"))
    monkeypatch.delenv("SELVA_IMPECCABLE_ALLOW_NPX", raising=False)
    result = await ImpeccableDetectTool().execute(repo_path=str(repo), paths=["web/page.tsx"])
    assert result.success is False
    assert result.data["status"] == "unavailable"
    assert "not installed" in (result.error or "")


async def test_rejects_paths_outside_the_workspace(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPECCABLE_BIN", str(_fake_engine(tmp_path)))
    outside = tmp_path / "outside.css"
    outside.write_text("a{}")
    (repo / "web" / "link.css").symlink_to(outside)
    result = await ImpeccableDetectTool().execute(
        repo_path=str(repo),
        paths=[
            "../outside.css",
            str(outside),
            "https://example.com",
            "--cdp",
            "web/link.css",
            "web/missing.css",
            "api.py",
        ],
    )
    reasons = {r["path"]: r["reason"] for r in result.data["rejected_paths"]}
    assert set(reasons) == {
        "../outside.css",
        str(outside),
        "https://example.com",
        "--cdp",
        "web/link.css",
        "web/missing.css",
        "api.py",
    }
    assert result.data["status"] == "no_ui_files"
    assert not (tmp_path / "record" / "argv").exists()


async def test_derives_changed_ui_files_from_git(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPECCABLE_BIN", str(_fake_engine(tmp_path)))

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", ".")
    git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "init")
    (repo / "web" / "page.tsx").write_text("export const P = () => <h2>Hi</h2>;\n")
    (repo / "web" / "new.css").write_text("a { color: red; }\n")
    (repo / "api.py").write_text("x = 2\n")

    result = await ImpeccableDetectTool().execute(repo_path=str(repo))
    assert sorted(result.data["files_scanned"]) == ["web/new.css", "web/page.tsx"]
    assert result.data["rejected_paths"] == []
