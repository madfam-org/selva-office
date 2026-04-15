"""Meeting notes workflow graph -- transcribe, summarize, extract action items."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from ..event_emitter import instrumented_node
from .base import BaseGraphState
from .base import run_async as _run_async

logger = logging.getLogger(__name__)


# -- State --------------------------------------------------------------------


class MeetingState(BaseGraphState, TypedDict, total=False):
    """Extended state for the meeting notes workflow."""

    transcript: str
    summary: str
    action_items: list[dict[str, str]]
    recording_url: str


# -- Node functions -----------------------------------------------------------


@instrumented_node
def transcribe(state: MeetingState) -> MeetingState:
    """Transcribe the meeting recording.

    Attempts LLM-based transcription from the recording URL or description.
    Falls back to a placeholder transcript when no LLM is configured.
    """
    messages = state.get("messages", [])
    recording_url = state.get("recording_url", "")
    description = state.get("description", "")

    # Try real STT first if recording_url points to an audio file on disk
    if recording_url and recording_url.startswith("/"):
        try:
            from autoswarm_tools.builtins.stt import SpeechToTextTool

            tool = SpeechToTextTool()
            result = _run_async(tool.execute(audio_path=recording_url))
            if result.success and result.output:
                transcript = result.output
                transcribe_msg = AIMessage(
                    content=f"Transcription completed via Whisper ({len(transcript)} chars).",
                    additional_kwargs={"action_category": "api_call"},
                )
                return {
                    **state,
                    "messages": [*messages, transcribe_msg],
                    "transcript": transcript,
                    "status": "transcribed",
                }
        except Exception:
            logger.debug("STT tool unavailable, falling back to LLM", exc_info=True)

    try:
        from autoswarm_workers.inference import call_llm, get_model_router

        router = get_model_router()
        prompt_content = (
            f"Transcribe the following meeting recording.\n"
            f"Recording URL: {recording_url}\n"
            f"Description: {description}\n"
            f"Provide a detailed transcript of the meeting."
        )
        transcript = _run_async(
            call_llm(
                router,
                messages=[{"role": "user", "content": prompt_content}],
                system_prompt=(
                    "You are a transcription assistant. "
                    "Transcribe the meeting recording accurately."
                ),
                task_type="research",
                agent_id=state.get("agent_id"),
                task_id=state.get("task_id"),
            )
        )
    except Exception as exc:
        logger.warning("Transcription LLM call failed: %s. Using placeholder.", exc)
        transcript = (
            f"[Placeholder transcript for meeting]\n"
            f"Recording: {recording_url or 'N/A'}\n"
            f"Description: {description or 'N/A'}\n"
            f"[Transcription service unavailable — manual transcript required]"
        )

    transcribe_msg = AIMessage(
        content=f"Transcription completed ({len(transcript)} chars).",
        additional_kwargs={"action_category": "api_call"},
    )
    return {
        **state,
        "messages": [*messages, transcribe_msg],
        "transcript": transcript,
        "status": "transcribed",
    }


@instrumented_node
def summarize(state: MeetingState) -> MeetingState:
    """Summarize the meeting transcript.

    Uses the LLM to create a concise summary of key discussion points.
    Falls back to returning the first 500 characters of the transcript.
    """
    messages = state.get("messages", [])
    transcript = state.get("transcript", "")

    if not transcript:
        error_msg = AIMessage(content="Cannot summarize: no transcript available.")
        return {
            **state,
            "messages": [*messages, error_msg],
            "summary": "",
            "status": "error",
        }

    try:
        from autoswarm_workers.inference import call_llm, get_model_router

        router = get_model_router()
        summary = _run_async(
            call_llm(
                router,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Summarize this meeting transcript into key discussion "
                            f"points. Be concise but thorough.\n\n"
                            f"TRANSCRIPT:\n{transcript}"
                        ),
                    },
                ],
                system_prompt=(
                    "You are a meeting summarizer. Create a concise summary "
                    "of the key discussion points."
                ),
                task_type="research",
                agent_id=state.get("agent_id"),
                task_id=state.get("task_id"),
            )
        )
    except Exception as exc:
        logger.warning("Summary LLM call failed: %s. Using fallback.", exc)
        summary = (
            f"[Auto-summary unavailable]\n\n"
            f"Transcript excerpt:\n{transcript[:500]}"
        )

    summary_msg = AIMessage(
        content="Meeting summary generated.",
        additional_kwargs={"action_category": "api_call"},
    )
    return {
        **state,
        "messages": [*messages, summary_msg],
        "summary": summary,
        "status": "summarized",
    }


@instrumented_node
def extract_actions(state: MeetingState) -> MeetingState:
    """Extract action items from the transcript and summary.

    Returns a list of dicts with ``task``, ``assignee``, and ``deadline`` keys.
    Falls back to an empty list when the LLM is unavailable.
    """
    messages = state.get("messages", [])
    transcript = state.get("transcript", "")
    summary = state.get("summary", "")

    try:
        from autoswarm_workers.inference import call_llm, get_model_router

        router = get_model_router()
        raw = _run_async(
            call_llm(
                router,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Extract action items from this meeting. Return a JSON "
                            f"array where each item has: task, assignee, deadline.\n\n"
                            f"SUMMARY:\n{summary}\n\n"
                            f"TRANSCRIPT:\n{transcript}"
                        ),
                    },
                ],
                system_prompt=(
                    "You are a task extraction assistant. Extract action items "
                    "with assignees and deadlines from the meeting transcript "
                    "and summary. Return valid JSON only."
                ),
                task_type="research",
                agent_id=state.get("agent_id"),
                task_id=state.get("task_id"),
            )
        )
        action_items = _parse_action_items(raw)
    except Exception as exc:
        logger.warning("Action extraction LLM call failed: %s.", exc)
        action_items = []

    actions_msg = AIMessage(
        content=f"Extracted {len(action_items)} action items.",
        additional_kwargs={"action_category": "api_call"},
    )
    return {
        **state,
        "messages": [*messages, actions_msg],
        "action_items": action_items,
        "status": "actions_extracted",
    }


@instrumented_node
def save_artifact(state: MeetingState) -> MeetingState:
    """Save the meeting notes as an artifact via ArtifactStorage.

    Persists the combined summary + action items + transcript to disk
    and sets ``state["result"]`` with the meeting notes data.
    """
    messages = state.get("messages", [])
    summary = state.get("summary", "")
    action_items = state.get("action_items", [])
    transcript = state.get("transcript", "")

    notes_data: dict[str, Any] = {
        "summary": summary,
        "action_items": action_items,
        "transcript": transcript,
    }
    notes_json = json.dumps(notes_data, indent=2)
    content_bytes = notes_json.encode("utf-8")
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    artifact_path: str | None = None
    try:
        from autoswarm_tools.storage.local import LocalFSStorage

        storage = LocalFSStorage()
        artifact_path = _run_async(storage.save(content_bytes, content_hash))
        logger.info("Meeting notes saved to artifact: %s", artifact_path)
    except Exception as exc:
        logger.warning("Failed to save meeting notes artifact: %s", exc)

    save_msg = AIMessage(
        content=(
            f"Meeting notes saved"
            f"{' to ' + artifact_path if artifact_path else ' (in-memory only)'}."
        ),
        additional_kwargs={"action_category": "api_call"},
    )
    return {
        **state,
        "messages": [*messages, save_msg],
        "result": notes_data,
        "status": "completed",
    }


# -- Helpers ------------------------------------------------------------------


def _parse_action_items(raw: str) -> list[dict[str, str]]:
    """Best-effort parse of LLM output into action item dicts."""
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [
                {
                    "task": item.get("task", ""),
                    "assignee": item.get("assignee", ""),
                    "deadline": item.get("deadline", ""),
                }
                for item in parsed
                if isinstance(item, dict)
            ]
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse action items JSON; returning empty list.")
    return []


# -- Graph construction -------------------------------------------------------


def build_meeting_graph() -> StateGraph[MeetingState]:
    """Construct the meeting notes workflow state graph.

    Flow::

        transcribe -> summarize -> extract_actions -> save_artifact -> END
    """
    graph: StateGraph[MeetingState] = StateGraph(MeetingState)

    graph.add_node("transcribe", transcribe)
    graph.add_node("summarize", summarize)
    graph.add_node("extract_actions", extract_actions)
    graph.add_node("save_artifact", save_artifact)

    graph.set_entry_point("transcribe")
    graph.add_edge("transcribe", "summarize")
    graph.add_edge("summarize", "extract_actions")
    graph.add_edge("extract_actions", "save_artifact")
    graph.add_edge("save_artifact", END)

    return graph
