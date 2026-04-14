"""
Next-Tier: Context Compression

Mirrors Hermes Agent's context_compressor.py — lossy sliding-window
summarization of the middle turns in a long conversation, preserving
the system prompt (turn 0) and the most recent N turns unchanged.

Prevents context window overflows in long ACP runs without losing
semantic continuity. Uses the configured LLM to summarize elided turns.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Turns to preserve unchanged at the head and tail (system + first user turn; last N turns)
_KEEP_HEAD = 2
_KEEP_TAIL = 6
_SUMMARY_MAX_TOKENS = 256
_COMPRESS_THRESHOLD = 20  # Compress when message count exceeds this


def _should_compress(messages: list[dict]) -> bool:
    return len(messages) > _COMPRESS_THRESHOLD


def _extract_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


class ContextCompressor:
    """
    Compresses the middle section of a message list by LLM summarization.

    Strategy:
      1. Keep messages[0 : _KEEP_HEAD]  (system prompt + first user message)
      2. Summarize messages[_KEEP_HEAD : -_KEEP_TAIL]  into one synthetic message
      3. Keep messages[-_KEEP_TAIL :]   (most recent turns verbatim)

    This is identical to the approach used in Hermes Agent's
    context_compressor.py and preserves Anthropic prompt-prefix caching
    compatibility by keeping the head segment unchanged.
    """

    def __init__(
        self,
        keep_head: int = _KEEP_HEAD,
        keep_tail: int = _KEEP_TAIL,
        compress_threshold: int = _COMPRESS_THRESHOLD,
    ) -> None:
        self._keep_head = keep_head
        self._keep_tail = keep_tail
        self._threshold = compress_threshold

    async def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Compress *messages* if above the threshold.

        Returns the original list unchanged if compression is not needed.
        """
        if len(messages) <= self._threshold:
            return messages

        head = messages[: self._keep_head]
        middle = messages[self._keep_head : -self._keep_tail]
        tail = messages[-self._keep_tail :]

        if not middle:
            return messages

        summary_text = await self._summarize(middle)
        summary_message = {
            "role": "assistant",
            "content": (
                f"[CONTEXT SUMMARY — {len(middle)} turns elided]\n\n{summary_text}"
            ),
        }

        compressed = head + [summary_message] + tail
        logger.info(
            "ContextCompressor: %d messages → %d (elided %d, summary %d chars).",
            len(messages),
            len(compressed),
            len(middle),
            len(summary_text),
        )
        return compressed

    async def _summarize(self, messages: list[dict[str, Any]]) -> str:
        """Call the LLM to summarize the elided middle turns."""
        transcript = "\n".join(
            f"{msg.get('role', 'unknown').upper()}: {_extract_text(msg)[:500]}"
            for msg in messages
        )
        summarization_prompt = (
            "Summarize the following conversation turns in under 200 words. "
            "Preserve all key decisions, facts, file paths, and action outcomes. "
            "Be dense, not verbose.\n\n"
            f"{transcript}"
        )

        try:
            from madfam_inference import get_default_router  # type: ignore
            from madfam_inference.types import InferenceRequest, RoutingPolicy, Sensitivity

            request = InferenceRequest(
                messages=[{"role": "user", "content": summarization_prompt}],
                system_prompt="You are a summarization assistant. Be concise and precise.",
                policy=RoutingPolicy(
                    sensitivity=Sensitivity.INTERNAL,
                    task_type="summarization",
                    temperature=0.1,
                    max_tokens=_SUMMARY_MAX_TOKENS,
                ),
            )
            router = get_default_router()
            response = await router.complete(request)
            return response.content
        except Exception as exc:
            logger.warning("ContextCompressor: LLM summarization failed (%s) — using truncated transcript.", exc)
            return transcript[:600] + "\n[... further context elided ...]"

    def compress_sync(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Synchronous wrapper for use inside sync node functions."""
        import asyncio
        try:
            return asyncio.run(self.compress(messages))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.compress(messages))
