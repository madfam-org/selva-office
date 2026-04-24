"""Tests for Meta-Harness integration tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.meta_harness import (
    MetaHarnessBudgetGateTool,
    MetaHarnessConvergenceCheckTool,
    MetaHarnessEscalateTierTool,
    MetaHarnessRoleSummaryTool,
    MetaHarnessRouteTool,
    MetaHarnessSubmitRoundTool,
    get_meta_harness_tools,
)


class TestRegistry:
    def test_six_tools_exported(self) -> None:
        tools = get_meta_harness_tools()
        names = {t.name for t in tools}
        assert names == {
            "meta_harness_budget_gate",
            "meta_harness_route",
            "meta_harness_role_summary",
            "meta_harness_convergence_check",
            "meta_harness_submit_round",
            "meta_harness_escalate_tier",
        }

    def test_schemas_valid(self) -> None:
        for t in get_meta_harness_tools():
            s = t.parameters_schema()
            assert s["type"] == "object"
            assert "properties" in s
            assert "required" in s

    def test_required_fields_match_spec(self) -> None:
        schemas = {t.name: t.parameters_schema() for t in get_meta_harness_tools()}
        assert set(schemas["meta_harness_budget_gate"]["required"]) == {
            "model",
            "iterations",
            "candidates_per_iteration",
            "eval_set_size",
            "input_tokens_per_eval",
            "output_tokens_per_eval",
        }
        assert schemas["meta_harness_route"]["required"] == []
        assert schemas["meta_harness_role_summary"]["required"] == ["session_id"]
        assert schemas["meta_harness_convergence_check"]["required"] == ["session_id"]
        assert set(schemas["meta_harness_submit_round"]["required"]) == {
            "session_id",
            "role",
            "content",
        }
        assert set(schemas["meta_harness_escalate_tier"]["required"]) == {
            "session_id",
            "current_tier",
            "reason",
        }


# -- budget gate -------------------------------------------------------------


class TestBudgetGate:
    @pytest.mark.asyncio
    async def test_happy_path_allow_under_threshold(self) -> None:
        estimate_json = '{"run": {"model": "x"}, "estimate": {"total_usd": 0.5}}'
        with patch(
            "selva_tools.builtins.meta_harness._run_cli",
            new=AsyncMock(return_value=(0, estimate_json, "")),
        ):
            r = await MetaHarnessBudgetGateTool().execute(
                model="openrouter/openai/gpt-oss-120b",
                iterations=1,
                candidates_per_iteration=5,
                eval_set_size=100,
                input_tokens_per_eval=1000,
                output_tokens_per_eval=250,
                agent_tier="allow",
                hard_cap_usd=10.0,
            )
            assert r.success is True
            assert r.data["decision"] == "allow"
            assert r.data["total_usd"] == 0.5

    @pytest.mark.asyncio
    async def test_over_hard_cap_deny(self) -> None:
        estimate_json = '{"estimate": {"total_usd": 500.0}, "run": {}}'
        with patch(
            "selva_tools.builtins.meta_harness._run_cli",
            new=AsyncMock(return_value=(0, estimate_json, "")),
        ):
            r = await MetaHarnessBudgetGateTool().execute(
                model="opus-4.6",
                iterations=1,
                candidates_per_iteration=5,
                eval_set_size=100,
                input_tokens_per_eval=1000,
                output_tokens_per_eval=250,
                agent_tier="allow",
                hard_cap_usd=10.0,
            )
            assert r.success is True
            assert r.data["decision"] == "deny"

    @pytest.mark.asyncio
    async def test_mid_range_asks(self) -> None:
        estimate_json = '{"estimate": {"total_usd": 3.25}, "run": {}}'
        with patch(
            "selva_tools.builtins.meta_harness._run_cli",
            new=AsyncMock(return_value=(0, estimate_json, "")),
        ):
            r = await MetaHarnessBudgetGateTool().execute(
                model="m",
                iterations=1,
                candidates_per_iteration=5,
                eval_set_size=100,
                input_tokens_per_eval=1000,
                output_tokens_per_eval=250,
                agent_tier="ask",
            )
            assert r.data["decision"] == "ask"

    @pytest.mark.asyncio
    async def test_cli_failure_bubbles_up(self) -> None:
        with patch(
            "selva_tools.builtins.meta_harness._run_cli",
            new=AsyncMock(return_value=(127, "", "harness directory not found")),
        ):
            r = await MetaHarnessBudgetGateTool().execute(
                model="m",
                iterations=1,
                candidates_per_iteration=1,
                eval_set_size=1,
                input_tokens_per_eval=1,
                output_tokens_per_eval=1,
            )
            assert r.success is False
            assert "harness directory not found" in (r.error or "")

    @pytest.mark.asyncio
    async def test_malformed_json_surfaced(self) -> None:
        with patch(
            "selva_tools.builtins.meta_harness._run_cli",
            new=AsyncMock(return_value=(0, "not json", "")),
        ):
            r = await MetaHarnessBudgetGateTool().execute(
                model="m",
                iterations=1,
                candidates_per_iteration=1,
                eval_set_size=1,
                input_tokens_per_eval=1,
                output_tokens_per_eval=1,
            )
            assert r.success is False
            assert "could not parse" in (r.error or "")


# -- route -------------------------------------------------------------------


class TestRoute:
    @pytest.mark.asyncio
    async def test_selva_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SELVA_API_BASE", "https://selva.town/v1")
        monkeypatch.setenv("SELVA_API_KEY", "sk-test")
        monkeypatch.delenv("MADFAM_INFERENCE_PROVIDER", raising=False)
        monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
        r = await MetaHarnessRouteTool().execute()
        assert r.success is True
        assert r.data["provider"] == "selva"
        assert r.data["base_url"] == "https://selva.town/v1"
        assert r.data["api_key_present"] is True

    @pytest.mark.asyncio
    async def test_deepinfra_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SELVA_API_BASE", raising=False)
        monkeypatch.delenv("SELVA_API_KEY", raising=False)
        monkeypatch.delenv("MADFAM_INFERENCE_PROVIDER", raising=False)
        monkeypatch.setenv("DEEPINFRA_API_KEY", "k")
        r = await MetaHarnessRouteTool().execute()
        assert r.success is True
        assert r.data["provider"] == "deepinfra"

    @pytest.mark.asyncio
    async def test_no_provider_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in (
            "SELVA_API_BASE",
            "SELVA_API_KEY",
            "DEEPINFRA_API_KEY",
            "MADFAM_INFERENCE_PROVIDER",
        ):
            monkeypatch.delenv(v, raising=False)
        r = await MetaHarnessRouteTool().execute()
        assert r.success is False
        assert "no inference provider" in (r.error or "").lower()

    @pytest.mark.asyncio
    async def test_explicit_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SELVA_API_BASE", "https://selva.town/v1")
        monkeypatch.setenv("SELVA_API_KEY", "sk-test")
        monkeypatch.setenv("DEEPINFRA_API_KEY", "k")
        monkeypatch.delenv("MADFAM_INFERENCE_PROVIDER", raising=False)
        r = await MetaHarnessRouteTool().execute(prefer_provider="deepinfra")
        assert r.data["provider"] == "deepinfra"


# -- role summary / convergence / submit / escalate --------------------------


class TestRoleSummaryAndConvergence:
    @pytest.mark.asyncio
    async def test_role_summary_stub_happy(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_HARNESS_DIR", str(tmp_path))
        r = await MetaHarnessRoleSummaryTool().execute(session_id="s1")
        assert r.success is True
        assert r.data["stub"] is True
        assert len(r.data["roles"]) == 9

    @pytest.mark.asyncio
    async def test_role_summary_missing_dir(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "does-not-exist"
        monkeypatch.setenv("META_HARNESS_DIR", str(missing))
        r = await MetaHarnessRoleSummaryTool().execute(session_id="s1")
        assert r.success is False
        assert "not found" in (r.error or "")

    @pytest.mark.asyncio
    async def test_convergence_stub(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_HARNESS_DIR", str(tmp_path))
        r = await MetaHarnessConvergenceCheckTool().execute(
            session_id="s1",
            required_roles=["build_run", "growth_market"],
            disagreement_threshold=0.1,
        )
        assert r.success is True
        assert r.data["converged"] is False
        assert r.data["disagreement_threshold"] == 0.1
        assert set(r.data["missing_roles"]) == {"build_run", "growth_market"}


class TestSubmitRound:
    @pytest.mark.asyncio
    async def test_submit_round_appends_jsonl(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("META_HARNESS_DIR", str(tmp_path))
        r = await MetaHarnessSubmitRoundTool().execute(
            session_id="s42",
            role="build_run",
            content="draft output",
            confidence=0.8,
            metadata={"source": "test"},
        )
        assert r.success is True
        assert r.data["stub"] is True
        recorded = tmp_path / "approvals" / "rounds-s42.jsonl"
        assert recorded.exists()
        line = recorded.read_text().strip()
        assert '"session_id": "s42"' in line
        assert '"role": "build_run"' in line

    @pytest.mark.asyncio
    async def test_submit_round_missing_harness(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "nope"
        monkeypatch.setenv("META_HARNESS_DIR", str(missing))
        r = await MetaHarnessSubmitRoundTool().execute(session_id="s1", role="r", content="c")
        assert r.success is False


class TestEscalateTier:
    @pytest.mark.asyncio
    async def test_escalate_happy(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_HARNESS_DIR", str(tmp_path))
        r = await MetaHarnessEscalateTierTool().execute(
            session_id="s1",
            current_tier="allow",
            requested_tier="ask",
            reason="we got reverted twice in a row",
        )
        assert r.success is True
        p = tmp_path / "approvals" / "escalations-s1.jsonl"
        assert p.exists()
        assert "we got reverted" in p.read_text()

    @pytest.mark.asyncio
    async def test_escalate_refuses_loosening(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("META_HARNESS_DIR", str(tmp_path))
        r = await MetaHarnessEscalateTierTool().execute(
            session_id="s1",
            current_tier="ask",
            requested_tier="allow",
            reason="trust me bro",
        )
        assert r.success is False
        assert "looser" in (r.error or "")

    @pytest.mark.asyncio
    async def test_escalate_missing_harness(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("META_HARNESS_DIR", str(tmp_path / "nope"))
        r = await MetaHarnessEscalateTierTool().execute(
            session_id="s1",
            current_tier="allow",
            requested_tier="ask",
            reason="x",
        )
        assert r.success is False
