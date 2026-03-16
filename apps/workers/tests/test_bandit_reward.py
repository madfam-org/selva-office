"""Tests for bandit reward signal (PR 4: Agent Learning Loop)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_settings():
    return MagicMock(
        bandit_persist_path="/tmp/test-bandit.json",
    )


class TestBanditRewardValues:
    """Verify correct reward values are passed to the bandit."""

    @pytest.mark.asyncio
    async def test_success_reward_1_0(self) -> None:
        mock_bandit = MagicMock()

        with (
            patch("autoswarm_workers.config.get_settings", return_value=_mock_settings()),
            patch("autoswarm_orchestrator.bandit.ThompsonBandit", return_value=mock_bandit),
        ):
            from autoswarm_workers.learning import update_bandit_reward

            await update_bandit_reward("agent-1", 1.0)
            mock_bandit.update.assert_called_once_with("agent-1", 1.0)

    @pytest.mark.asyncio
    async def test_failure_reward_0_0(self) -> None:
        mock_bandit = MagicMock()

        with (
            patch("autoswarm_workers.config.get_settings", return_value=_mock_settings()),
            patch("autoswarm_orchestrator.bandit.ThompsonBandit", return_value=mock_bandit),
        ):
            from autoswarm_workers.learning import update_bandit_reward

            await update_bandit_reward("agent-2", 0.0)
            mock_bandit.update.assert_called_once_with("agent-2", 0.0)

    @pytest.mark.asyncio
    async def test_partial_reward_0_2(self) -> None:
        mock_bandit = MagicMock()

        with (
            patch("autoswarm_workers.config.get_settings", return_value=_mock_settings()),
            patch("autoswarm_orchestrator.bandit.ThompsonBandit", return_value=mock_bandit),
        ):
            from autoswarm_workers.learning import update_bandit_reward

            await update_bandit_reward("agent-3", 0.2)
            mock_bandit.update.assert_called_once_with("agent-3", 0.2)

    @pytest.mark.asyncio
    async def test_skip_unknown_agent(self) -> None:
        with patch(
            "autoswarm_orchestrator.bandit.ThompsonBandit",
        ) as mock_cls:
            from autoswarm_workers.learning import update_bandit_reward

            await update_bandit_reward("unknown", 1.0)
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_graceful_on_bandit_error(self) -> None:
        with (
            patch("autoswarm_workers.config.get_settings", return_value=_mock_settings()),
            patch(
                "autoswarm_orchestrator.bandit.ThompsonBandit",
                side_effect=RuntimeError("disk full"),
            ),
        ):
            from autoswarm_workers.learning import update_bandit_reward

            # Should not raise
            await update_bandit_reward("agent-1", 1.0)
