"""Tests for ThompsonBandit agent selection."""

from __future__ import annotations

import json
import random
from collections import Counter

import pytest

from autoswarm_orchestrator.bandit import ThompsonBandit


class TestThompsonBanditBasics:
    """Core bandit functionality."""

    def test_select_single_candidate(self) -> None:
        bandit = ThompsonBandit()
        result = bandit.select(["agent-1"])
        assert result == "agent-1"

    def test_select_returns_from_candidates(self) -> None:
        bandit = ThompsonBandit()
        candidates = ["a1", "a2", "a3"]
        result = bandit.select(candidates)
        assert result in candidates

    def test_empty_candidates_raises(self) -> None:
        bandit = ThompsonBandit()
        with pytest.raises(ValueError, match="No candidates"):
            bandit.select([])

    def test_initial_uniform_prior(self) -> None:
        bandit = ThompsonBandit()
        bandit._ensure_arm("agent-1")
        stats = bandit.get_stats()
        assert stats["agent-1"]["alpha"] == 1.0
        assert stats["agent-1"]["beta"] == 1.0

    def test_get_stats_empty(self) -> None:
        bandit = ThompsonBandit()
        assert bandit.get_stats() == {}


class TestThompsonBanditUpdates:
    """Update mechanics for reward/failure tracking."""

    def test_update_increases_alpha_on_reward(self) -> None:
        bandit = ThompsonBandit()
        bandit.update("agent-1", reward=1.0)
        stats = bandit.get_stats()
        assert stats["agent-1"]["alpha"] == 2.0
        assert stats["agent-1"]["beta"] == 1.0

    def test_update_increases_beta_on_failure(self) -> None:
        bandit = ThompsonBandit()
        bandit.update("agent-1", reward=0.0)
        stats = bandit.get_stats()
        assert stats["agent-1"]["alpha"] == 1.0
        assert stats["agent-1"]["beta"] == 2.0

    def test_multiple_updates(self) -> None:
        bandit = ThompsonBandit()
        bandit.update("agent-1", reward=1.0)
        bandit.update("agent-1", reward=1.0)
        bandit.update("agent-1", reward=0.0)
        stats = bandit.get_stats()
        # alpha: 1.0 + 1.0 + 1.0 + 0.0 = 3.0
        assert stats["agent-1"]["alpha"] == 3.0
        # beta: 1.0 + 0.0 + 0.0 + 1.0 = 2.0
        assert stats["agent-1"]["beta"] == 2.0

    def test_partial_reward(self) -> None:
        bandit = ThompsonBandit()
        bandit.update("agent-1", reward=0.5)
        stats = bandit.get_stats()
        assert stats["agent-1"]["alpha"] == 1.5
        assert stats["agent-1"]["beta"] == 1.5


class TestThompsonBanditConvergence:
    """Statistical convergence of Thompson Sampling."""

    def test_convergence_to_best_arm(self) -> None:
        """After many trials, the best arm should be selected most often."""
        bandit = ThompsonBandit()
        random.seed(42)

        # Agent-good gets high rewards, agent-bad gets low rewards
        for _ in range(100):
            bandit.update("agent-good", reward=0.9)
            bandit.update("agent-bad", reward=0.1)

        # Now select 1000 times and verify the good agent is chosen more
        counts: Counter[str] = Counter()
        for _ in range(1000):
            selected = bandit.select(["agent-good", "agent-bad"])
            counts[selected] += 1

        assert counts["agent-good"] > counts["agent-bad"]
        # The good agent should be selected the vast majority of the time
        assert counts["agent-good"] > 900


class TestThompsonBanditPersistence:
    """File-based persistence for bandit state."""

    def test_persistence_save_load(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        persist_file = str(tmp_path / "bandit_state.json")

        # Create and train a bandit
        bandit = ThompsonBandit(persist_path=persist_file)
        bandit.update("agent-1", reward=1.0)
        bandit.update("agent-2", reward=0.0)

        # Load into a new instance
        bandit2 = ThompsonBandit(persist_path=persist_file)
        stats = bandit2.get_stats()
        assert stats["agent-1"]["alpha"] == 2.0
        assert stats["agent-2"]["beta"] == 2.0

    def test_persistence_file_created(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        persist_file = tmp_path / "subdir" / "bandit.json"
        bandit = ThompsonBandit(persist_path=str(persist_file))
        bandit.update("agent-1", reward=1.0)
        assert persist_file.exists()
        data = json.loads(persist_file.read_text())
        assert "agent-1" in data

    def test_missing_persist_file_starts_fresh(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        persist_file = str(tmp_path / "nonexistent.json")
        bandit = ThompsonBandit(persist_path=persist_file)
        assert bandit.get_stats() == {}
