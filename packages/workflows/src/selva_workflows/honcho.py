"""
Dialectic User Profiling — inspired by the Hermes Agent / Honcho integration.

The HonchoProfiler maintains a lightweight, expanding model of each operator's
interaction style and injects tailored behavioral addendums into swarm system
prompts, so every agent session is contextually tuned to its human partner.

In production this data lives in the EdgeMemoryDB (SQLite FTS5 store).  The
profiler reads historical transcripts keyed by ``user_id`` and synthesizes a
compact preference profile, which is then serialised into a system prompt
fragment that any LangGraph node can prepend to its chain.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default preference schema
# ---------------------------------------------------------------------------

DEFAULT_PROFILE: dict[str, Any] = {
    "verbosity": "concise",          # "concise" | "verbose"
    "code_style": "pep8",            # "pep8" | "google" | "numpy"
    "review_strictness": "moderate", # "lenient" | "moderate" | "strict"
    "preferred_language": "python",
    "defensive_assertions": True,
    "custom_notes": [],
}


class HonchoProfiler:
    """
    Lightweight dialectic user modelling layer.

    Usage::

        profiler = HonchoProfiler(memory_store)
        addendum = profiler.get_system_addendum(user_id="aldo")
        # Prepend `addendum` to any LangGraph node's system prompt.
    """

    def __init__(self, memory_store: Any | None = None) -> None:
        """
        Args:
            memory_store: An ``EdgeMemoryDB`` instance.  When ``None`` the
                profiler operates in stub mode (useful for tests).
        """
        self._store = memory_store
        self._cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Profile retrieval
    # ------------------------------------------------------------------

    def get_profile(self, user_id: str) -> dict[str, Any]:
        """
        Return the behavioral profile for ``user_id``.

        Resolution order:
        1. In-process cache (avoids redundant DB reads in the same run).
        2. EdgeMemoryDB FTS search over historical transcripts.
        3. DEFAULT_PROFILE fallback.
        """
        if user_id in self._cache:
            return self._cache[user_id]

        profile = dict(DEFAULT_PROFILE)

        if self._store is not None:
            try:
                hits = self._store.fts_search(f"user_preference {user_id}", limit=5)
                for hit in hits:
                    # Preference hints are stored as pipe-delimited key=value pairs
                    # e.g.  "user_preference aldo verbosity=verbose | review_strictness=strict"
                    self._parse_preference_hit(hit.get("content", ""), profile)
            except Exception as exc:
                logger.warning("HonchoProfiler: DB lookup failed for %s — %s", user_id, exc)

        self._cache[user_id] = profile
        return profile

    def update_profile(self, user_id: str, key: str, value: Any) -> None:
        """
        Optimistically update the in-memory cache and persist a preference
        marker to the EdgeMemoryDB so future sessions inherit the update.
        """
        profile = self.get_profile(user_id)
        profile[key] = value
        self._cache[user_id] = profile

        if self._store is not None:
            try:
                self._store.insert_transcript(
                    run_id=f"profile-{user_id}",
                    agent_role="honcho",
                    role="system",
                    content=f"user_preference {user_id} {key}={value}",
                )
            except Exception as exc:
                logger.warning("HonchoProfiler: failed to persist preference — %s", exc)

    # ------------------------------------------------------------------
    # System prompt injection
    # ------------------------------------------------------------------

    def get_system_addendum(self, user_id: str) -> str:
        """
        Synthesise a compact behavioral system-prompt fragment for the given
        user.  Prepend this to any LangGraph swarm node's system prompt.
        """
        p = self.get_profile(user_id)

        notes_block = ""
        if p["custom_notes"]:
            notes_block = "\n".join(f"- {n}" for n in p["custom_notes"])
            notes_block = f"\nAdditional operator notes:\n{notes_block}"

        return (
            f"[Operator Profile — {user_id}]\n"
            f"Response verbosity: {p['verbosity']}.\n"
            f"Code style convention: {p['code_style']}.\n"
            f"Review strictness: {p['review_strictness']}.\n"
            f"Preferred language: {p['preferred_language']}.\n"
            f"Include defensive assertions: {p['defensive_assertions']}."
            f"{notes_block}\n"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_preference_hit(content: str, profile: dict[str, Any]) -> None:
        """Parse a ``key=value`` preference pair from a stored transcript."""
        for token in content.split("|"):
            token = token.strip()
            if "=" in token:
                k, _, v = token.partition("=")
                k = k.strip()
                v = v.strip()
                if k in profile:
                    # Attempt type coercion for known boolean fields
                    if isinstance(profile[k], bool):
                        profile[k] = v.lower() in ("true", "1", "yes")
                    else:
                        profile[k] = v
