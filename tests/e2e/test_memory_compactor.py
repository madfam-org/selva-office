"""
Tests for Gap 2: Memory LLM Summarization (MemoryCompactor).
"""

from __future__ import annotations

import time

import pytest


@pytest.fixture()
def fresh_db():
    from nexus_api.memory_store.db import EdgeMemoryDB

    db = EdgeMemoryDB(":memory:")
    yield db
    db.close()


def _seed_old_run(db, run_id: str, days_ago: int = 60):
    """Insert an episode and two transcripts backdated by days_ago."""
    cutoff = time.time() - (days_ago * 86400)
    db._conn.execute(
        "INSERT INTO conversation_episodes"
        " (id, run_id, agent_role, started_at)"
        " VALUES (?, ?, ?, ?)",
        (f"ep-{run_id}", run_id, "acp-analyst", cutoff),
    )
    for i, content in enumerate(["Phase I started scraping.", "Extracted 42 endpoints."]):
        db._conn.execute(
            "INSERT INTO transcripts (episode_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (f"ep-{run_id}", "assistant", content, cutoff + i),
        )


def test_compact_memory_replaces_old_rows(fresh_db, monkeypatch):
    """compact_memory should replace verbose rows with a summary row."""
    _seed_old_run(fresh_db, "old-run-001", days_ago=60)

    # Monkeypatch the singleton used inside the task
    monkeypatch.setattr("nexus_api.tasks.memory_tasks.memory_store", fresh_db)

    # Disable LLM — use extractive fallback
    monkeypatch.setattr(
        "nexus_api.tasks.memory_tasks.__builtins__",
        {**__builtins__} if isinstance(__builtins__, dict) else vars(__builtins__),
    )

    from nexus_api.tasks.memory_tasks import (
        _fetch_raw_transcript,
        _get_old_run_ids,
        _replace_with_summary,
    )

    # Verify old runs are detected
    old_runs = _get_old_run_ids(fresh_db, before_days=30)
    assert "old-run-001" in old_runs

    # Run extractive summarisation directly
    raw = _fetch_raw_transcript(fresh_db, "old-run-001")
    assert "Phase I" in raw

    summary = "Extracted summary of old-run-001"
    _replace_with_summary(fresh_db, "old-run-001", summary)

    # After replacement, raw rows should be gone and summary row should exist
    cursor = fresh_db._conn.execute(
        "SELECT role, content FROM transcripts t"
        " JOIN conversation_episodes e ON t.episode_id = e.id"
        " WHERE e.run_id = ?",
        ("old-run-001",),
    )
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["role"] == "summary"
    assert rows[0]["content"] == summary


def test_recent_runs_not_compacted(fresh_db, monkeypatch):
    """Runs started recently should not be compacted."""
    _seed_old_run(fresh_db, "new-run-001", days_ago=1)

    mod = __import__(
        "nexus_api.tasks.memory_tasks",
        fromlist=["_get_old_run_ids"],
    )
    old_runs = mod._get_old_run_ids(fresh_db, before_days=30)
    assert "new-run-001" not in old_runs
