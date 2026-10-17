"""Anthropic adapter against the current model generation.

Current models reject caller-chosen sampling params, an explicit
``thinking: disabled`` / ``budget_tokens`` and assistant prefill; usage
carries prompt-cache counters; ``stop_reason: refusal`` must fail loudly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from madfam_inference.providers.anthropic import (
    AnthropicProvider,
    AnthropicRefusalError,
    accepts_sampling_params,
)
from madfam_inference.router import _is_fallback_eligible
from madfam_inference.types import InferenceRequest, RoutingPolicy, StreamUsage

CURRENT_MODELS = [
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-haiku-5-5",
    # dated / future point releases inherit the family rule
    "claude-opus-5-5-20261001",
    "claude-sonnet-5-7",
    "claude-fable-6",
]
LEGACY_MODELS = ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"]

LONG_SYSTEM = "You are Selva's planner. " * 400  # well above the cache threshold


def _request(model: str | None, **kwargs: Any) -> InferenceRequest:
    return InferenceRequest(
        messages=kwargs.pop("messages", [{"role": "user", "content": "hola"}]),
        policy=RoutingPolicy(model_override=model, temperature=0.4),
        **kwargs,
    )


def _body(model: str | None, **kwargs: Any) -> dict[str, Any]:
    return AnthropicProvider(api_key="test-key")._build_body(_request(model, **kwargs))


@pytest.mark.parametrize("model", CURRENT_MODELS)
def test_current_models_get_no_sampling_params(model: str) -> None:
    assert not accepts_sampling_params(model)
    body = _body(model)
    for key in ("temperature", "top_p", "top_k"):
        assert key not in body


@pytest.mark.parametrize("model", CURRENT_MODELS + LEGACY_MODELS)
def test_thinking_is_never_sent(model: str) -> None:
    body = _body(model)
    assert "thinking" not in body
    assert "budget_tokens" not in str(body)


@pytest.mark.parametrize("model", LEGACY_MODELS)
def test_legacy_models_keep_temperature(model: str) -> None:
    assert accepts_sampling_params(model)
    assert _body(model)["temperature"] == 0.4


def test_default_model_is_current_and_omits_temperature() -> None:
    body = _body(None)
    assert body["model"] == "claude-sonnet-5-5"
    assert "temperature" not in body


def test_long_system_prompt_is_sent_with_cache_control() -> None:
    body = _body("claude-opus-5-5", system_prompt=LONG_SYSTEM)
    assert body["system"] == [
        {"type": "text", "text": LONG_SYSTEM, "cache_control": {"type": "ephemeral"}}
    ]


def test_short_system_prompt_stays_plain_string() -> None:
    assert _body("claude-opus-5-5", system_prompt="Be brief.")["system"] == "Be brief."


def test_system_role_messages_are_hoisted() -> None:
    body = _body(
        "claude-opus-5-5",
        system_prompt="Base.",
        messages=[
            {"role": "system", "content": "Extra rules."},
            {"role": "user", "content": "hola"},
        ],
    )
    assert body["system"] == "Base.\n\nExtra rules."
    assert [m["role"] for m in body["messages"]] == ["user"]


def test_no_assistant_prefill_for_current_models() -> None:
    body = _body(
        "claude-opus-5-5",
        messages=[
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "partial"},
        ],
    )
    assert body["messages"][-1]["role"] == "user"


# ── complete(): usage + refusal ────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._data


def _patch_post(monkeypatch: pytest.MonkeyPatch, data: dict[str, Any]) -> list[dict]:
    sent: list[dict] = []

    async def _post(self, url, **kwargs):  # noqa: ANN001
        sent.append(kwargs["json"])
        return _FakeResponse(data)

    async def _aenter(self):  # noqa: ANN001
        return self

    async def _aexit(self, *exc):  # noqa: ANN001
        return False

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    monkeypatch.setattr(httpx.AsyncClient, "__aenter__", _aenter)
    monkeypatch.setattr(httpx.AsyncClient, "__aexit__", _aexit)
    return sent


@pytest.mark.asyncio
async def test_complete_captures_cache_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_post(
        monkeypatch,
        {
            "model": "claude-opus-5-5",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {
                "input_tokens": 12,
                "output_tokens": 34,
                "cache_read_input_tokens": 5000,
                "cache_creation_input_tokens": 700,
            },
        },
    )
    resp = await AnthropicProvider(api_key="k").complete(_request("claude-opus-5-5"))
    assert resp.content == "ok"
    assert resp.usage == {
        "input_tokens": 12,
        "output_tokens": 34,
        "cache_read_input_tokens": 5000,
        "cache_creation_input_tokens": 700,
    }


@pytest.mark.asyncio
async def test_complete_refusal_raises_and_is_not_fallback_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(
        monkeypatch,
        {
            "model": "claude-opus-5-5",
            "stop_reason": "refusal",
            "content": [],
            "usage": {"input_tokens": 10, "output_tokens": 0},
        },
    )
    with pytest.raises(AnthropicRefusalError) as excinfo:
        await AnthropicProvider(api_key="k").complete(_request("claude-opus-5-5"))
    assert "refus" in str(excinfo.value)
    assert not _is_fallback_eligible(excinfo.value)


# ── stream(): cache usage + refusal ────────────────────────────────────────


class _FakeStream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line


def _patch_stream(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> None:
    @asynccontextmanager
    async def _stream(self, method, url, **kwargs):  # noqa: ANN001
        yield _FakeStream(lines)

    async def _aenter(self):  # noqa: ANN001
        return self

    async def _aexit(self, *exc):  # noqa: ANN001
        return False

    monkeypatch.setattr(httpx.AsyncClient, "stream", _stream)
    monkeypatch.setattr(httpx.AsyncClient, "__aenter__", _aenter)
    monkeypatch.setattr(httpx.AsyncClient, "__aexit__", _aexit)


def _sse(stop_reason: str) -> list[str]:
    return [
        'data: {"type":"message_start","message":{"model":"claude-opus-5-5","usage":'
        '{"input_tokens":3,"cache_read_input_tokens":900,"cache_creation_input_tokens":40}}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"' + stop_reason + '"},'
        '"usage":{"output_tokens":7}}',
    ]


@pytest.mark.asyncio
async def test_stream_reports_cache_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(monkeypatch, _sse("end_turn"))
    seen: list[StreamUsage] = []
    chunks = [
        c
        async for c in AnthropicProvider(api_key="k").stream(
            _request("claude-opus-5-5"), on_usage=seen.append
        )
    ]
    assert chunks == ["hi"]
    assert seen[0].cache_read_input_tokens == 900
    assert seen[0].cache_creation_input_tokens == 40
    assert (seen[0].input_tokens, seen[0].output_tokens) == (3, 7)


@pytest.mark.asyncio
async def test_stream_refusal_raises_after_reporting_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_stream(monkeypatch, _sse("refusal"))
    seen: list[StreamUsage] = []
    with pytest.raises(AnthropicRefusalError):
        async for _ in AnthropicProvider(api_key="k").stream(
            _request("claude-opus-5-5"), on_usage=seen.append
        ):
            pass
    assert seen and seen[0].output_tokens == 7
