"""Tests for `_build_llm_event_payload` — the helper that shapes the
payload shipped inside ``llm.response`` observability events.

Contract this must hold (mirrors office-ui PR #23's extractLlmPreview):
- RESTRICTED sensitivity returns None (text never hits the event bus).
- INTERNAL / PUBLIC return a dict with ``response_text`` +
  ``prompt_snippet`` keys when the source strings are non-empty.
- Both are capped at LLM_EVENT_TEXT_MAX_CHARS (800) with `…` ellipsis.
- prompt_snippet prefers the last user-role message; falls back to
  the last message of any role.
- Whitespace-only strings are dropped.
- Empty-messages / empty-content input returns None rather than an
  empty dict.
"""

from __future__ import annotations

from madfam_inference.types import Sensitivity
from selva_workers.inference import (
    LLM_EVENT_TEXT_MAX_CHARS,
    _build_llm_event_payload,
)


def test_restricted_sensitivity_returns_none() -> None:
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "hola"}],
        response_content="bienvenido",
        sensitivity=Sensitivity.RESTRICTED,
    )
    assert payload is None


def test_internal_returns_response_and_prompt() -> None:
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "ping?"}],
        response_content="pong",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload == {
        "response_text": "pong",
        "prompt_snippet": "ping?",
    }


def test_public_returns_response_and_prompt() -> None:
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "ping?"}],
        response_content="pong",
        sensitivity=Sensitivity.PUBLIC,
    )
    assert payload is not None
    assert payload["response_text"] == "pong"
    assert payload["prompt_snippet"] == "ping?"


def test_prompt_snippet_prefers_last_user_message() -> None:
    messages = [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "first user msg"},
        {"role": "assistant", "content": "sure"},
        {"role": "user", "content": "second user msg"},
        {"role": "assistant", "content": "ok"},
    ]
    payload = _build_llm_event_payload(
        messages=messages,
        response_content="fine",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert payload["prompt_snippet"] == "second user msg"


def test_prompt_snippet_falls_back_to_last_message_when_no_user_role() -> None:
    messages = [
        {"role": "system", "content": "be nice"},
        {"role": "assistant", "content": "hello"},
    ]
    payload = _build_llm_event_payload(
        messages=messages,
        response_content="ack",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert payload["prompt_snippet"] == "hello"


def test_truncates_response_over_limit() -> None:
    long = "x" * (LLM_EVENT_TEXT_MAX_CHARS + 400)
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "go"}],
        response_content=long,
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert len(payload["response_text"]) == LLM_EVENT_TEXT_MAX_CHARS + 1  # +ellipsis
    assert payload["response_text"].endswith("…")


def test_does_not_truncate_at_exact_limit() -> None:
    exact = "y" * LLM_EVENT_TEXT_MAX_CHARS
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "go"}],
        response_content=exact,
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert payload["response_text"] == exact
    assert not payload["response_text"].endswith("…")


def test_truncates_prompt_over_limit() -> None:
    long_prompt = "p" * (LLM_EVENT_TEXT_MAX_CHARS + 100)
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": long_prompt}],
        response_content="short",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert len(payload["prompt_snippet"]) == LLM_EVENT_TEXT_MAX_CHARS + 1
    assert payload["prompt_snippet"].endswith("…")


def test_strips_whitespace_before_capping() -> None:
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "   padded prompt   "}],
        response_content="   padded response   ",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert payload["response_text"] == "padded response"
    assert payload["prompt_snippet"] == "padded prompt"


def test_whitespace_only_fields_are_dropped() -> None:
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "   \n\t  "}],
        response_content="   ",
        sensitivity=Sensitivity.INTERNAL,
    )
    # Both sides blank → nothing worth emitting.
    assert payload is None


def test_response_present_prompt_missing_returns_response_only() -> None:
    payload = _build_llm_event_payload(
        messages=[],
        response_content="hello",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload == {"response_text": "hello"}


def test_prompt_present_response_missing_returns_prompt_only() -> None:
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "hi?"}],
        response_content="",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload == {"prompt_snippet": "hi?"}


def test_preserves_non_ascii() -> None:
    payload = _build_llm_event_payload(
        messages=[{"role": "user", "content": "¿Cómo estás?"}],
        response_content="Hóla — muy bien, gracias!",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert payload["response_text"] == "Hóla — muy bien, gracias!"
    assert payload["prompt_snippet"] == "¿Cómo estás?"


def test_non_string_prompt_content_is_stringified() -> None:
    # Multimodal message with structured content blocks — stringify so
    # the preview has something meaningful rather than '<list>' in the
    # UI. Extractor on the UI side is tolerant of format.
    payload = _build_llm_event_payload(
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": "look at this image"}],
            },
        ],
        response_content="sure",
        sensitivity=Sensitivity.INTERNAL,
    )
    assert payload is not None
    assert "prompt_snippet" in payload
    assert "look at this image" in payload["prompt_snippet"]
