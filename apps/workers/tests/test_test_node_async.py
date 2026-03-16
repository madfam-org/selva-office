"""Tests for Phase 1: test() node uses _run_async instead of get_event_loop."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch


@dataclass
class FakeBashResult:
    """Minimal BashResult stand-in for testing."""

    success: bool
    return_code: int
    stdout: str
    stderr: str = ""


class TestTestNodeUsesRunAsync:
    """Verify that test() calls _run_async rather than asyncio.get_event_loop."""

    def test_uses_run_async_not_get_event_loop(self) -> None:
        """The test() node source must NOT contain asyncio.get_event_loop."""
        import inspect

        from autoswarm_workers.graphs.coding import test

        # Get the wrapped function (under @instrumented_node)
        fn = getattr(test, "__wrapped__", test)
        source = inspect.getsource(fn)
        assert "get_event_loop" not in source, (
            "test() node still uses asyncio.get_event_loop() — "
            "it should use _run_async() instead"
        )
        assert "_run_async" in source

    def test_returns_pytest_results_on_success(self) -> None:
        """test() node should return results from BashTool when pytest passes."""
        bash_result = FakeBashResult(
            success=True,
            return_code=0,
            stdout="3 passed in 0.5s",
        )

        mock_bash = MagicMock()
        mock_bash.execute = AsyncMock(return_value=bash_result)

        with (
            patch("autoswarm_workers.graphs.coding._bash_tool", mock_bash),
            patch(
                "autoswarm_workers.event_emitter.emit_event",
                new_callable=AsyncMock,
            ),
            patch(
                "autoswarm_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from autoswarm_workers.graphs.coding import test

            state = {
                "messages": [],
                "iteration": 1,
                "worktree_path": "/tmp/wt",
                "task_id": "t1",
                "agent_id": "a1",
            }
            result = test(state)

            assert result["test_results"]["source"] == "pytest"
            assert result["test_results"]["passed"] is True

    def test_returns_pytest_failure_results(self) -> None:
        """test() node should report failure when pytest has failures."""
        bash_result = FakeBashResult(
            success=False,
            return_code=1,
            stdout="1 failed, 2 passed in 0.5s",
            stderr="",
        )

        mock_bash = MagicMock()
        mock_bash.execute = AsyncMock(return_value=bash_result)

        with (
            patch("autoswarm_workers.graphs.coding._bash_tool", mock_bash),
            patch(
                "autoswarm_workers.event_emitter.emit_event",
                new_callable=AsyncMock,
            ),
            patch(
                "autoswarm_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from autoswarm_workers.graphs.coding import test

            state = {
                "messages": [],
                "iteration": 1,
                "worktree_path": "/tmp/wt",
                "task_id": "t1",
                "agent_id": "a1",
            }
            result = test(state)

            assert result["test_results"]["source"] == "pytest"
            assert result["test_results"]["passed"] is False

    def test_falls_back_to_simulated_on_exception(self) -> None:
        """test() node falls back to simulated results when BashTool raises."""
        mock_bash = MagicMock()
        mock_bash.execute = AsyncMock(side_effect=RuntimeError("no bash"))

        with (
            patch("autoswarm_workers.graphs.coding._bash_tool", mock_bash),
            patch(
                "autoswarm_workers.event_emitter.emit_event",
                new_callable=AsyncMock,
            ),
            patch(
                "autoswarm_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from autoswarm_workers.graphs.coding import test

            state = {
                "messages": [],
                "iteration": 1,
                "worktree_path": None,
                "task_id": "t1",
                "agent_id": "a1",
            }
            result = test(state)

            assert result["test_results"]["source"] == "simulated"
