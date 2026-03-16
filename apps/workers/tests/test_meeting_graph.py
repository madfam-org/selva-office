"""Tests for the meeting notes workflow graph (PR 6.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


class TestMeetingGraphStructure:
    """Meeting graph has correct nodes and edges."""

    def test_build_meeting_graph(self) -> None:
        from autoswarm_workers.graphs.meeting import build_meeting_graph

        graph = build_meeting_graph()
        node_names = set(graph.nodes.keys())
        assert "transcribe" in node_names
        assert "summarize" in node_names
        assert "extract_actions" in node_names
        assert "save_artifact" in node_names

    def test_graph_compiles(self) -> None:
        from autoswarm_workers.graphs.meeting import build_meeting_graph

        graph = build_meeting_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_meeting_state_fields(self) -> None:
        from autoswarm_workers.graphs.meeting import MeetingState

        annotations = MeetingState.__annotations__
        assert "transcript" in annotations
        assert "summary" in annotations
        assert "action_items" in annotations
        assert "recording_url" in annotations


class TestTranscribeNode:
    """transcribe() generates a transcript from the recording."""

    def test_transcribe_node_fallback(self) -> None:
        """When no LLM is configured, transcribe returns a placeholder."""
        from autoswarm_workers.graphs.meeting import transcribe

        with patch(
            "autoswarm_workers.inference.get_model_router",
            side_effect=RuntimeError("no providers"),
        ):
            result = transcribe({
                "messages": [],
                "recording_url": "https://example.com/meeting.webm",
                "description": "Sprint planning",
            })

        assert result["status"] == "transcribed"
        assert result["transcript"]
        assert "Sprint planning" in result["transcript"] or "Placeholder" in result["transcript"]
        assert len(result["messages"]) == 1

    def test_transcribe_with_llm(self) -> None:
        """When an LLM is configured, transcribe uses it."""
        from autoswarm_workers.graphs.meeting import transcribe

        mock_router = AsyncMock()
        with (
            patch(
                "autoswarm_workers.inference.get_model_router",
                return_value=mock_router,
            ),
            patch(
                "autoswarm_workers.inference.call_llm",
                new_callable=AsyncMock,
                return_value="Alice: Let's discuss the roadmap.\nBob: Agreed.",
            ),
        ):
            result = transcribe({
                "messages": [],
                "recording_url": "https://example.com/meeting.webm",
                "description": "Roadmap discussion",
            })

        assert result["status"] == "transcribed"
        assert "roadmap" in result["transcript"].lower()


class TestSummarizeNode:
    """summarize() generates a summary from the transcript."""

    def test_summarize_node(self) -> None:
        """summarize returns a summary using fallback when LLM unavailable."""
        from autoswarm_workers.graphs.meeting import summarize

        result = summarize({
            "messages": [],
            "transcript": "Alice: We need to fix the login bug. Bob: I agree.",
        })

        assert result["status"] == "summarized"
        assert result["summary"]
        assert len(result["messages"]) == 1

    def test_summarize_empty_transcript(self) -> None:
        """summarize with empty transcript returns error status."""
        from autoswarm_workers.graphs.meeting import summarize

        result = summarize({
            "messages": [],
            "transcript": "",
        })

        assert result["status"] == "error"
        assert result["summary"] == ""


class TestExtractActionsNode:
    """extract_actions() extracts action items from the meeting."""

    def test_extract_actions_node(self) -> None:
        """extract_actions returns a list of action items."""
        from autoswarm_workers.graphs.meeting import extract_actions

        result = extract_actions({
            "messages": [],
            "transcript": "Alice: Bob will fix the bug by Friday.",
            "summary": "Discussion about bug fixes.",
        })

        assert result["status"] == "actions_extracted"
        assert isinstance(result["action_items"], list)
        assert len(result["messages"]) == 1

    def test_extract_actions_with_llm(self) -> None:
        """extract_actions parses LLM JSON output correctly."""
        from autoswarm_workers.graphs.meeting import extract_actions

        mock_json = '[{"task": "Fix login bug", "assignee": "Bob", "deadline": "Friday"}]'
        with (
            patch(
                "autoswarm_workers.inference.get_model_router",
                return_value=AsyncMock(),
            ),
            patch(
                "autoswarm_workers.inference.call_llm",
                new_callable=AsyncMock,
                return_value=mock_json,
            ),
        ):
            result = extract_actions({
                "messages": [],
                "transcript": "Alice: Bob will fix the bug by Friday.",
                "summary": "Bug fix discussion.",
            })

        assert result["status"] == "actions_extracted"
        assert len(result["action_items"]) == 1
        assert result["action_items"][0]["task"] == "Fix login bug"
        assert result["action_items"][0]["assignee"] == "Bob"


class TestSaveArtifactNode:
    """save_artifact() persists meeting notes."""

    def test_save_artifact_node(self) -> None:
        """save_artifact saves notes and sets result."""
        from autoswarm_workers.graphs.meeting import save_artifact

        result = save_artifact({
            "messages": [],
            "transcript": "Meeting transcript here.",
            "summary": "Summary of the meeting.",
            "action_items": [{"task": "Do thing", "assignee": "Alice", "deadline": "Monday"}],
        })

        assert result["status"] == "completed"
        assert result["result"] is not None
        assert result["result"]["summary"] == "Summary of the meeting."
        assert len(result["result"]["action_items"]) == 1
        assert result["result"]["transcript"] == "Meeting transcript here."


class TestMeetingRegistration:
    """Meeting graph is registered in __main__.py."""

    def test_meeting_in_graph_builders(self) -> None:
        from autoswarm_workers.__main__ import GRAPH_BUILDERS

        assert "meeting" in GRAPH_BUILDERS

    def test_meeting_timeout_configured(self) -> None:
        from autoswarm_redis_pool.timeout import DEFAULT_TIMEOUTS

        assert "meeting" in DEFAULT_TIMEOUTS
        assert DEFAULT_TIMEOUTS["meeting"] == 300


class TestParseActionItems:
    """_parse_action_items handles various LLM output formats."""

    def test_valid_json(self) -> None:
        from autoswarm_workers.graphs.meeting import _parse_action_items

        raw = '[{"task": "Write tests", "assignee": "Dev", "deadline": "EOW"}]'
        result = _parse_action_items(raw)
        assert len(result) == 1
        assert result[0]["task"] == "Write tests"

    def test_json_with_code_fences(self) -> None:
        from autoswarm_workers.graphs.meeting import _parse_action_items

        raw = '```json\n[{"task": "Deploy", "assignee": "Ops", "deadline": "Monday"}]\n```'
        result = _parse_action_items(raw)
        assert len(result) == 1
        assert result[0]["task"] == "Deploy"

    def test_invalid_json(self) -> None:
        from autoswarm_workers.graphs.meeting import _parse_action_items

        raw = "This is not valid JSON"
        result = _parse_action_items(raw)
        assert result == []

    def test_empty_array(self) -> None:
        from autoswarm_workers.graphs.meeting import _parse_action_items

        raw = "[]"
        result = _parse_action_items(raw)
        assert result == []
