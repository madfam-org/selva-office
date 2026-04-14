"""
Gap 6: Trajectory Export — ShareGPT Format

Queries EdgeMemoryDB for all transcript rows in a run and serializes
them to the ShareGPT conversation format used by Atropos and other RL
training pipelines, enabling fine-tuning on cleanroom-derived ACP runs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ShareGPT role mapping
_ROLE_MAP = {
    "user": "human",
    "assistant": "gpt",
    "system": "system",
    "summary": "gpt",  # treat compacted summaries as assistant output
    "gateway-telegram": "human",
    "gateway-discord": "human",
    "gateway-slack": "human",
    "gateway-email": "human",
    "gateway-sms": "human",
    "acp-analyst": "gpt",
    "acp-sanitizer": "gpt",
    "acp-clean-swarm": "gpt",
    "acp-qa-oracle": "gpt",
}


class TrajectoryExporter:
    """
    Exports ACP run transcripts as ShareGPT-format conversation objects.

    ShareGPT format (per entry/line):
    {
        "id": "<run_id>",
        "conversations": [
            {"from": "human", "value": "..."},
            {"from": "gpt",   "value": "..."},
            ...
        ]
    }
    """

    def __init__(self, memory_store=None) -> None:
        if memory_store is None:
            from nexus_api.memory_store.db import memory_store as _ms
            self._store = _ms
        else:
            self._store = memory_store

    def build_sharegpt(self, run_id: str) -> dict:
        """
        Build a single ShareGPT trajectory for *run_id*.

        Returns:
            {"id": run_id, "conversations": [...]}
        """
        rows = self._fetch_transcript_rows(run_id)
        if not rows:
            logger.warning("No transcript rows found for run_id=%s", run_id)
            return {"id": run_id, "conversations": []}

        conversations = []
        for row in rows:
            role = _ROLE_MAP.get(row.get("role", ""), "gpt")
            content = row.get("content", "").strip()
            if content:
                conversations.append({"from": role, "value": content})

        return {"id": run_id, "conversations": conversations}

    def export_batch(self, run_ids: list[str], output_path: str) -> int:
        """
        Write a JSONL file with one ShareGPT trajectory per line.

        Returns:
            Number of trajectories written.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with out.open("w", encoding="utf-8") as f:
            for run_id in run_ids:
                traj = self.build_sharegpt(run_id)
                if traj["conversations"]:
                    f.write(json.dumps(traj, ensure_ascii=False) + "\n")
                    count += 1
        logger.info("Exported %d trajectories to %s", count, output_path)
        return count

    def list_exportable_runs(self) -> list[str]:
        """Return run_ids for completed ACP runs available for export."""
        try:
            cursor = self._store._conn.execute(
                "SELECT DISTINCT run_id FROM conversation_episodes ORDER BY started_at DESC"
            )
            return [row["run_id"] for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("Could not list exportable runs: %s", exc)
            return []

    def _fetch_transcript_rows(self, run_id: str) -> list[dict]:
        """Fetch all transcript rows for *run_id* ordered by timestamp."""
        try:
            cursor = self._store._conn.execute(
                """
                SELECT t.role, t.content, t.timestamp
                FROM transcripts t
                JOIN conversation_episodes e ON t.episode_id = e.id
                WHERE e.run_id = ?
                ORDER BY t.timestamp ASC
                """,
                (run_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("Could not fetch transcripts for run %s: %s", run_id, exc)
            return []
