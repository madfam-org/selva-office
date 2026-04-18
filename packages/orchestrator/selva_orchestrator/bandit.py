"""Thompson Sampling multi-armed bandit for agent selection."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)


class ThompsonBandit:
    """Thompson Sampling bandit for intelligent agent selection.

    Each arm (agent) has a Beta(alpha, beta) distribution.
    Higher alpha = more successes, higher beta = more failures.
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._arms: dict[str, dict[str, float]] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path and self._persist_path.exists():
            self._load()

    def _ensure_arm(self, agent_id: str) -> None:
        if agent_id not in self._arms:
            self._arms[agent_id] = {"alpha": 1.0, "beta": 1.0}  # Uniform prior

    def select(self, candidates: list[str]) -> str:
        """Sample from each candidate's Beta distribution and return the highest.

        If candidates is empty, raises ValueError.
        """
        if not candidates:
            raise ValueError("No candidates to select from")

        best_agent = ""
        best_sample = -1.0

        for agent_id in candidates:
            self._ensure_arm(agent_id)
            arm = self._arms[agent_id]
            sample = random.betavariate(arm["alpha"], arm["beta"])
            if sample > best_sample:
                best_sample = sample
                best_agent = agent_id

        return best_agent

    def update(self, agent_id: str, reward: float) -> None:
        """Update the Beta distribution for an agent based on outcome.

        reward should be between 0.0 and 1.0.
        """
        self._ensure_arm(agent_id)
        self._arms[agent_id]["alpha"] += reward
        self._arms[agent_id]["beta"] += 1.0 - reward
        if self._persist_path:
            self._save()

    def get_stats(self) -> dict[str, dict[str, float]]:
        """Return current alpha/beta stats for all arms."""
        return dict(self._arms)

    def _save(self) -> None:
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(json.dumps(self._arms, indent=2))

    def _load(self) -> None:
        if not self._persist_path:
            return
        try:
            data = json.loads(self._persist_path.read_text())
            self._arms = data
        except Exception:
            logger.warning("Failed to load bandit state from %s", self._persist_path)
