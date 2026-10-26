"""Test doubles for the autoheal agent: a recorded Enclii, a scripted model,
a fake Courier, and a placeholder config. Used by this package's tests and by
the nexus-api / workers tests. Nothing here reaches a network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .agent import LLMReply, LLMUnavailable
from .config import AutohealConfig

NOW = datetime(2026, 10, 24, 14, 5, tzinfo=UTC)


def price(provider: str, model: str, inp: int, out: int) -> float:
    """The shared cost model (``madfam_budget_gate``), as the worker uses it."""
    from madfam_budget_gate.cost_model import estimate_cost

    return float(estimate_cost(provider, model, inp, out))


def make_cfg(**overrides: Any) -> AutohealConfig:
    base: dict[str, Any] = {
        "enabled": True,
        "providers": ("anthropic-ops", "anthropic"),
        "incident_cap_usd": 1.0,  # placeholders, not the real caps
        "daily_cap_usd": 5.0,
        "alertnames": ("CNPGInstanceStatusUnreachable",),
        "courier_url": "https://courier.invalid",
        "courier_tenant": "tenant-placeholder",
        "courier_recipient": "chat-placeholder",
    }
    base.update(overrides)
    return AutohealConfig(**base)


class RecordedEnclii:
    """Answers from the recorded responses; records every request it gets."""

    def __init__(self, responses: dict[str, Any], plan_hash: str | None = None) -> None:
        self.responses = responses
        self.plan_hash = plan_hash
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []

    async def __call__(
        self, method: str, path: str, body: dict[str, Any] | None
    ) -> tuple[int, Any]:
        self.requests.append((method, path, body))
        ns = ((body or {}).get("scope") or {}).get("namespace")
        if path in ("/v1/ops/pods/restart", "/v1/ops/apps/sync"):
            return 200, {
                "operation_id": "op-plan",
                "audit_id": "aud-plan",
                "status": "planned",
                "dry_run": True,
                "data": {"plan_hash": self.plan_hash or "sha256:placeholder"},
            }
        for key in (f"{method} {path}#{ns}", f"{method} {path}"):
            if key in self.responses:
                return 200, self.responses[key]
        return 404, {"error": "not_found"}


class ScriptedLLM:
    """Returns the scripted replies in order; records what it was offered."""

    def __init__(
        self,
        replies: list[str | Exception],
        usage: dict[str, int] | None = None,
    ) -> None:
        self.replies = list(replies)
        self.usage = usage or {"input_tokens": 4000, "output_tokens": 600}
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        providers: tuple[str, ...],
        model: str,
        max_tokens: int,
        incident_key: str,
    ) -> LLMReply:
        self.calls.append(
            {"providers": providers, "model": model, "messages": [dict(m) for m in messages]}
        )
        if not self.replies:
            raise LLMUnavailable("script exhausted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMReply(content=reply, provider=providers[0], model=model, usage=dict(self.usage))


class FakeCourier:
    def __init__(self, status: int = 201) -> None:
        self.status = status
        self.sent: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    async def __call__(
        self, url: str, headers: dict[str, str], body: dict[str, Any]
    ) -> tuple[int, Any]:
        self.sent.append((url, headers, body))
        return self.status, {"delivery": {"id": f"dlv-{len(self.sent)}"}, "replayed": False}
