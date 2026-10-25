from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..base import InferenceProvider, UsageCallback
from ..caching import PromptCacheManager
from ..types import InferenceRequest, InferenceResponse, StreamUsage

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-sonnet-5-5"
ANTHROPIC_VERSION = "2023-06-01"

_cache_manager = PromptCacheManager()

# Current-generation models answer a caller-chosen sampling value
# (``temperature`` / ``top_p`` / ``top_k``) with a 400, and also reject an
# explicit ``thinking: {type: "disabled"}`` / ``budget_tokens`` and assistant
# prefill. The adapter therefore sends sampling params ONLY to the legacy
# models below and never sends ``thinking`` at all (the model default,
# adaptive thinking, applies). This is a family/version rule, not a list of
# ids, so a new dated or point release inherits the safe behaviour: any
# ``claude-*`` id not recognised as legacy gets no sampling params.
#
# Legacy (sampling accepted): Fable — never; Opus < 4.7; Sonnet < 5;
# Haiku < 5.5.
_MODEL_VERSION_RE = re.compile(
    r"^(?:[a-z]+[./])*claude-(?P<family>fable|opus|sonnet|haiku)-(?P<major>\d{1,2})"
    r"(?:-(?P<minor>\d{1,2}))?(?=$|[-@:])"
)
_SAMPLING_CUTOFF: dict[str, tuple[int, int]] = {
    # family -> first (major, minor) that REJECTS sampling params
    "fable": (0, 0),
    "opus": (4, 7),
    "sonnet": (5, 0),
    "haiku": (5, 5),
}

# Kept for callers that imported it: prefixes of the models known to reject
# sampling params. ``accepts_sampling_params`` is the rule actually applied.
NO_SAMPLING_MODEL_PREFIXES: tuple[str, ...] = (
    "claude-fable-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-5",
    "claude-haiku-5-5",
)


def accepts_sampling_params(model: str) -> bool:
    """Whether ``model`` accepts a caller-chosen ``temperature``.

    Only recognised legacy models do. Unknown or newer ids return False:
    leaving ``temperature`` out never causes a 400, sending it can.
    """
    match = _MODEL_VERSION_RE.match(model.strip().lower())
    if match is None:
        return False
    family = match.group("family")
    version = (int(match.group("major")), int(match.group("minor") or 0))
    return version < _SAMPLING_CUTOFF[family]


class AnthropicRefusalError(RuntimeError):
    """The model declined the request (``stop_reason: "refusal"``).

    Raised instead of returning empty text so the caller fails visibly.
    ``no_fallback`` tells the router not to re-send the same request to a
    different vendor: a policy refusal is an answer, not an outage.
    """

    no_fallback = True


class AnthropicProvider(InferenceProvider):
    """Inference provider for the Anthropic Messages API."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = ANTHROPIC_API_URL,
        timeout: float = 120.0,
        provider_name: str = "anthropic",
        credential_env: str | None = None,
    ) -> None:
        # ``provider_name`` is the registered name; an extra Anthropic account
        # (``anthropic-<suffix>``, see ``madfam_inference.credentials``) reports
        # its own name so responses, the USD ledger and the grant meter record
        # which account paid. ``credential_env`` is the env var the key came
        # from; the grant guard checks it against the grant's ``key_env``.
        self.name = provider_name
        self.credential_env = credential_env
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def supports_vision(self) -> bool:
        """Anthropic Claude models support vision natively."""
        return True

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert multimodal message content to Anthropic's native format.

        - Plain string content is wrapped as ``[{"type": "text", "text": ...}]``.
        - List content blocks are converted:
          - ``text`` blocks -> ``{"type": "text", "text": ...}``
          - ``image_base64`` blocks -> ``{"type": "image", "source":
            {"type": "base64", "media_type": ..., "data": ...}}``
          - ``image_url`` blocks -> ``{"type": "image", "source":
            {"type": "url", "url": ...}}``
        """
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str) or content is None:
                text = content or ""
                formatted.append(
                    {
                        **msg,
                        "content": [{"type": "text", "text": text}],
                    }
                )
                continue

            # content is a list of blocks
            anthropic_blocks: list[dict[str, Any]] = []
            for block in content:
                block_type = block.get("type", "")
                if block_type == "text":
                    anthropic_blocks.append({"type": "text", "text": block["content"]})
                elif block_type == "image_base64":
                    mime = block.get("mime_type", "image/png")
                    anthropic_blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": block["content"],
                            },
                        }
                    )
                elif block_type == "image_url":
                    anthropic_blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": block["content"],
                            },
                        }
                    )
                else:
                    if "content" in block:
                        anthropic_blocks.append({"type": "text", "text": block["content"]})

            formatted.append({**msg, "content": anthropic_blocks})
        return formatted

    @staticmethod
    def _split_system(
        request: InferenceRequest,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Hoist ``role: system`` messages into the system prompt.

        The Messages API rejects ``system`` inside ``messages``; callers that
        build OpenAI-style histories (the YAML agent node) can send one.
        """
        system_parts: list[str] = [request.system_prompt] if request.system_prompt else []
        rest: list[dict[str, Any]] = []
        for msg in request.messages:
            if msg.get("role") == "system":
                content = msg.get("content")
                if isinstance(content, str) and content:
                    system_parts.append(content)
                continue
            rest.append(msg)
        return "\n\n".join(system_parts), rest

    def _build_body(self, request: InferenceRequest, *, stream: bool = False) -> dict[str, Any]:
        system_prompt, raw_messages = self._split_system(request)
        messages = self._format_messages(raw_messages)
        model = request.policy.model_override or self._model
        sampling = accepts_sampling_params(model)
        if not sampling and messages and messages[-1].get("role") == "assistant":
            # Current models reject assistant prefill. Never send one: close
            # the turn with a user message so the model continues instead.
            messages.append({"role": "user", "content": [{"type": "text", "text": "Continue."}]})
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": request.policy.max_tokens,
            "messages": messages,
        }
        if sampling:
            body["temperature"] = request.policy.temperature
        # ``thinking`` is deliberately never sent: current models 400 on
        # ``{"type": "disabled"}`` and on ``budget_tokens``; the model default
        # (adaptive) applies.
        if system_prompt:
            # Prompt caching: a stable system prompt (skills + persona) long
            # enough to cache is sent as a content block marked
            # ``cache_control: ephemeral``; shorter ones stay a plain string.
            _, system_block = _cache_manager.apply_cache_breakpoints(
                [], system_prompt=system_prompt, provider="anthropic"
            )
            body["system"] = system_block
        if request.tools:
            body["tools"] = request.tools
        if stream:
            body["stream"] = True
        return body

    @staticmethod
    def _refusal_error(model: str) -> AnthropicRefusalError:
        return AnthropicRefusalError(
            f"Anthropic model {model} refused the request (stop_reason=refusal); "
            "no output was produced."
        )

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        body = self._build_body(request)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/messages",
                headers=self._headers(),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract text from content blocks
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append(block)

        model = data.get("model", body["model"])
        if data.get("stop_reason") == "refusal":
            raise self._refusal_error(model)

        usage_data = data.get("usage", {}) or {}
        return InferenceResponse(
            content="".join(text_parts),
            model=model,
            provider=self.name,
            usage={
                "input_tokens": int(usage_data.get("input_tokens") or 0),
                "output_tokens": int(usage_data.get("output_tokens") or 0),
                "cache_read_input_tokens": int(usage_data.get("cache_read_input_tokens") or 0),
                "cache_creation_input_tokens": int(
                    usage_data.get("cache_creation_input_tokens") or 0
                ),
            },
            tool_calls=tool_calls if tool_calls else None,
        )

    async def stream(
        self,
        request: InferenceRequest,
        on_usage: UsageCallback | None = None,
    ) -> AsyncIterator[str]:
        body = self._build_body(request, stream=True)

        usage = StreamUsage()
        saw_usage = False
        refused = False
        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream(
                "POST",
                f"{self._base_url}/messages",
                headers=self._headers(),
                json=body,
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: ") :]
                if payload.strip() == "[DONE]":
                    break
                # Parse SSE event - Anthropic sends content_block_delta events
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta.get("text", "")
                elif event_type == "message_start":
                    # Carries the resolved model + input token count.
                    message = event.get("message", {})
                    usage.model = message.get("model") or usage.model
                    start_usage = message.get("usage", {}) or {}
                    if "input_tokens" in start_usage:
                        usage.input_tokens = int(start_usage["input_tokens"] or 0)
                        saw_usage = True
                    usage.cache_read_input_tokens = int(
                        start_usage.get("cache_read_input_tokens") or 0
                    )
                    usage.cache_creation_input_tokens = int(
                        start_usage.get("cache_creation_input_tokens") or 0
                    )
                elif event_type == "message_delta":
                    if (event.get("delta") or {}).get("stop_reason") == "refusal":
                        refused = True
                    # usage.output_tokens here is cumulative — last one wins.
                    delta_usage = event.get("usage", {}) or {}
                    if "output_tokens" in delta_usage:
                        usage.output_tokens = int(delta_usage["output_tokens"] or 0)
                        saw_usage = True

        # Tokens were consumed even on a refusal, so report usage first.
        if on_usage is not None and saw_usage:
            on_usage(usage)
        if refused:
            raise self._refusal_error(usage.model or body["model"])

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/models",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
            # Fallback to known models if endpoint not available
            return [
                "claude-fable-5-1",
                "claude-opus-5-5",
                "claude-sonnet-5-5",
                "claude-haiku-5-5",
            ]
