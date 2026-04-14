"""
E2E tests — Gap 6: Trajectory Export (ShareGPT format)
"""
import json
import tempfile
from unittest.mock import MagicMock, patch
import pytest


_FAKE_TRANSCRIPTS = [
    {"role": "user", "content": "Initiate ACP for https://example.com", "timestamp": "2026-04-13T20:00:00Z"},
    {"role": "acp-analyst", "content": "Phase I analysis complete. PRD generated.", "timestamp": "2026-04-13T20:01:00Z"},
    {"role": "acp-clean-swarm", "content": "Phase III skill compiled successfully.", "timestamp": "2026-04-13T20:05:00Z"},
    {"role": "acp-qa-oracle", "content": "All tests passed. Skill approved.", "timestamp": "2026-04-13T20:10:00Z"},
]


class TestTrajectoryExporter:
    def _make_exporter(self):
        from autoswarm_workflows.trajectory import TrajectoryExporter
        mock_store = MagicMock()
        exporter = TrajectoryExporter(memory_store=mock_store)
        exporter._fetch_transcript_rows = MagicMock(return_value=_FAKE_TRANSCRIPTS)
        return exporter

    def test_build_sharegpt_structure(self):
        """build_sharegpt returns a valid ShareGPT dict with id and conversations."""
        exporter = self._make_exporter()
        traj = exporter.build_sharegpt("run-abc-123")
        assert traj["id"] == "run-abc-123"
        assert isinstance(traj["conversations"], list)
        assert len(traj["conversations"]) == len(_FAKE_TRANSCRIPTS)

    def test_role_mapping_human(self):
        """user role is mapped to 'human' in ShareGPT format."""
        exporter = self._make_exporter()
        traj = exporter.build_sharegpt("run-001")
        first = traj["conversations"][0]
        assert first["from"] == "human"

    def test_role_mapping_gpt(self):
        """acp-analyst role is mapped to 'gpt' in ShareGPT format."""
        exporter = self._make_exporter()
        traj = exporter.build_sharegpt("run-001")
        second = traj["conversations"][1]
        assert second["from"] == "gpt"

    def test_empty_run_returns_empty_conversations(self):
        """No transcripts → empty conversations list."""
        from autoswarm_workflows.trajectory import TrajectoryExporter
        mock_store = MagicMock()
        exporter = TrajectoryExporter(memory_store=mock_store)
        exporter._fetch_transcript_rows = MagicMock(return_value=[])
        traj = exporter.build_sharegpt("empty-run")
        assert traj["conversations"] == []

    def test_export_batch_writes_jsonl(self, tmp_path):
        """export_batch writes one valid JSON line per run."""
        exporter = self._make_exporter()
        out_path = str(tmp_path / "trajectories.jsonl")
        count = exporter.export_batch(["run-1", "run-2"], out_path)
        assert count == 2
        lines = open(out_path).readlines()
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert "id" in obj
            assert "conversations" in obj
            assert isinstance(obj["conversations"], list)
