"""Inference helper for LangGraph worker nodes."""

from __future__ import annotations

import contextlib
import contextvars
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from madfam_inference import InferenceRequest, InferenceResponse, ModelRouter
from madfam_inference.factory import build_router_from_env
from madfam_inference.types import RoutingPolicy, Sensitivity

from .config import get_settings

logger = logging.getLogger(__name__)


def build_model_router() -> ModelRouter:
    """Instantiate a ModelRouter with available providers from config.

    Delegates to the shared ``build_router_from_env`` factory in the
    inference package so that the worker and nexus-api proxy use
    identical provider registration logic.
    """
    settings = get_settings()
    return build_router_from_env(
        org_config_path=settings.org_config_path,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        openrouter_api_key=settings.openrouter_api_key,
        together_api_key=settings.together_api_key,
        fireworks_api_key=settings.fireworks_api_key,
        deepinfra_api_key=settings.deepinfra_api_key,
        siliconflow_api_key=settings.siliconflow_api_key,
        moonshot_api_key=settings.moonshot_api_key,
        groq_api_key=settings.groq_api_key,
        mistral_api_key=settings.mistral_api_key,
        ollama_base_url=settings.ollama_base_url,
    )


def validate_providers() -> None:
    """Log which providers are available. Warns if only Ollama is registered."""
    settings = get_settings()
    org_config_path = Path(settings.org_config_path).expanduser()
    if not org_config_path.exists():
        logger.warning(
            "Org config not found at %s — run 'make setup-org-config'. "
            "Task-type model routing is disabled.",
            org_config_path,
        )

    try:
        router = build_model_router()
        providers = router.available_providers
        cloud = [p for p in providers if p != "ollama"]
        if cloud:
            logger.info("LLM providers available: %s", ", ".join(providers))
        else:
            logger.warning(
                "No cloud LLM API keys configured — only Ollama is available. "
                "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or other provider keys "
                "in .env to enable cloud inference."
            )
    except Exception as exc:
        logger.warning("Failed to validate providers: %s", exc)


_router: ModelRouter | None = None


class LLMCallError(RuntimeError):
    """An LLM call failed and produced no content.

    Raised by :func:`call_llm` instead of returning placeholder text, so a
    graph node either degrades explicitly in its own ``except`` or fails;
    the failure is also recorded for the task (see :func:`with_task_org`)
    so the task record shows it.
    """


# The org id of the task this worker coroutine is running, bound by
# ``process_task`` for the whole graph run. ``call_llm`` reads it when a
# call site does not pass ``org_id`` explicitly, so every graph's LLM spend
# is attributed (and routed) to the task's tenant instead of ``default``.
_task_org_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "selva_task_org_id", default=None
)
# Failures of ``call_llm`` during the current task, appended in place (the
# list object is shared with copied contexts, e.g. LangGraph executor
# threads and ``run_async``).
_task_llm_failures: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "selva_task_llm_failures", default=None
)


@contextlib.contextmanager
def with_task_org(org_id: str | None) -> Iterator[list[dict[str, Any]]]:
    """Bind the task's org id for ``call_llm`` and collect its LLM failures.

    Yields the list that ``call_llm`` appends an ``{"error", "task_type",
    "model"}`` record to whenever a call fails.
    """
    failures: list[dict[str, Any]] = []
    org_token = _task_org_id.set(org_id or None)
    failures_token = _task_llm_failures.set(failures)
    try:
        yield failures
    finally:
        _task_org_id.reset(org_token)
        _task_llm_failures.reset(failures_token)


_MODEL_PROVIDER_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude-", "anthropic"),
    ("gpt-", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
)


def provider_for_model(model: str) -> str | None:
    """The provider that serves ``model``, when the id says so unambiguously."""
    m = model.strip().lower()
    for prefix, provider in _MODEL_PROVIDER_PREFIXES:
        if m.startswith(prefix):
            return provider
    return None


def _pin_model(router: ModelRouter, policy: RoutingPolicy, model: str) -> None:
    """Honour a caller-chosen model (a YAML node's ``model``) without widening routing.

    - A model id that names a provider (``claude-*`` → anthropic, ``gpt-*`` →
      openai) is honoured only when that provider is registered AND inside
      the set the request's sensitivity + org config already allow. It is
      then made primary through a server-side allowlist that is a subset of
      that set (the rest stay as fallback, on their default model). So a
      tenant whose org config allows only DeepInfra keeps DeepInfra.
    - Otherwise the pin is ignored with a WARNING (routing default applies).
    - An id that names no provider (e.g. ``meta-llama/...``) is passed as
      ``model_override`` to whatever provider routing picks.
    """
    provider = provider_for_model(model)
    if provider is None:
        policy.model_override = model
        return
    allowed_for = getattr(router, "allowed_providers_for", None)
    allowed = (
        allowed_for(InferenceRequest(messages=[], policy=policy)) if callable(allowed_for) else []
    )
    registered = set(getattr(router, "available_providers", []) or [])
    if provider not in allowed or provider not in registered:
        logger.warning(
            "Model pin %r ignored: provider %s is not available for org=%s "
            "(allowed: %s, registered: %s); default routing applies.",
            model,
            provider,
            policy.org_id,
            allowed,
            sorted(registered),
        )
        return
    policy.provider_allowlist = [provider] + [
        p for p in allowed if p != provider and p in registered and p != "ollama"
    ]
    policy.provider_models = {provider: model}


def resolve_task_org_id(org_id: str | None = None) -> str:
    """The org id an LLM call is attributed to: explicit, else task, else ``default``."""
    return org_id or _task_org_id.get() or "default"


# Max chars for response / prompt snippets shipped inside the `payload`
# of llm.response observability events. Chosen so a 280-char preview (the
# limit OpsFeed's `extractLlmPreview` truncates at) stays whole while the
# rest of the string is available via the per-task timeline endpoint.
LLM_EVENT_TEXT_MAX_CHARS = 800


def _build_llm_event_payload(
    *,
    messages: list[dict[str, Any]],
    response_content: str,
    sensitivity: Sensitivity,
) -> dict[str, Any] | None:
    """Assemble the `payload` field for an ``llm.response`` event.

    Returns None for RESTRICTED workloads so prompt / response text
    never reaches the event bus. For INTERNAL / PUBLIC, returns a
    dict with ``response_text`` (capped) and ``prompt_snippet`` (the
    last user-message content, capped). Extractor contract mirrors
    ``office-ui/src/components/OpsFeed.tsx::extractLlmPreview``.
    """
    if sensitivity == Sensitivity.RESTRICTED:
        return None

    def _cap(text: str) -> str:
        trimmed = (text or "").strip()
        if len(trimmed) <= LLM_EVENT_TEXT_MAX_CHARS:
            return trimmed
        return trimmed[:LLM_EVENT_TEXT_MAX_CHARS] + "…"

    payload: dict[str, Any] = {}
    response_capped = _cap(response_content)
    if response_capped:
        payload["response_text"] = response_capped

    # Use the last user-role message as the prompt snippet. Fall back to
    # the last message of any role if there is no user message, so tests
    # and single-message calls still get a preview.
    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"),
        messages[-1] if messages else None,
    )
    if last_user:
        raw = last_user.get("content")
        prompt_text = raw if isinstance(raw, str) else str(raw) if raw is not None else ""
        prompt_capped = _cap(prompt_text)
        if prompt_capped:
            payload["prompt_snippet"] = prompt_capped

    return payload or None


def get_model_router() -> ModelRouter:
    """Return a lazily-initialised singleton ``ModelRouter``."""
    global _router  # noqa: PLW0603
    if _router is None:
        _router = build_model_router()
    return _router


async def call_llm(
    router: ModelRouter,
    messages: list[dict[str, Any]],
    system_prompt: str = "",
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
    task_type: str | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
    org_id: str | None = None,
    response_format: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> str:
    """Call the LLM and return its content.

    ``org_id`` defaults to the org of the task being processed (bound by
    ``process_task`` via :func:`with_task_org`), so spend is attributed —
    and per-org routing applied — to the right tenant. ``model`` pins a
    model id for this call (a task-type assignment still wins, as for the
    gateway, so the pin applies to untyped calls — see :func:`_pin_model`);
    ``temperature`` overrides the default sampling temperature.

    Raises :class:`LLMCallError` when no provider answers. It never returns
    placeholder text: callers degrade explicitly in their own ``except`` or
    fail, and the failure is recorded on the task.

    When a response is received, token usage (with the provider/model, the
    input/output/cache split and the task type, from which nexus-api prices
    ``cost_usd``) is metered to the billing ledger.
    """
    resolved_org = resolve_task_org_id(org_id)
    try:
        import time as _time

        from .event_emitter import emit_event as _emit_llm_event

        _llm_start = _time.monotonic()

        policy = RoutingPolicy(
            sensitivity=sensitivity,
            task_type=task_type,
            org_id=resolved_org,
        )
        if temperature is not None:
            policy.temperature = temperature
        if model and task_type is None:
            # With a task type the org-config assignment decides the model,
            # exactly as for the gateway; the pin applies to untyped calls.
            _pin_model(router, policy, model)
        request = InferenceRequest(
            messages=messages,
            system_prompt=system_prompt or None,
            policy=policy,
            response_format=response_format,
        )
        response: InferenceResponse = await router.complete(request)

        _llm_elapsed = int((_time.monotonic() - _llm_start) * 1000)
        _total_tokens = (response.usage.get("total_tokens") or 0) if response.usage else 0

        # Emit LLM event for observability.
        #
        # Include truncated response + last-message prompt snippets so the
        # UI's OpsFeed (office-ui PR #23) can surface what the agent is
        # actually saying, not just metadata. Skipped when sensitivity is
        # RESTRICTED — those prompts / responses never hit the event bus.
        import contextlib

        from .config import get_settings as _get_llm_settings

        llm_payload = _build_llm_event_payload(
            messages=messages,
            response_content=response.content,
            sensitivity=sensitivity,
        )

        with contextlib.suppress(Exception):
            await _emit_llm_event(
                _get_llm_settings().nexus_api_url,
                event_type="llm.response",
                event_category="llm",
                task_id=task_id,
                agent_id=agent_id,
                provider=response.provider,
                model=response.model,
                token_count=_total_tokens,
                duration_ms=_llm_elapsed,
                payload=llm_payload,
            )

        # Meter the inference call to the billing ledger.
        if response.usage:
            from .metering import meter_inference_call

            await meter_inference_call(
                usage=response.usage,
                provider=response.provider,
                model=response.model,
                agent_id=agent_id,
                task_id=task_id,
                org_id=resolved_org,
                task_type=task_type,
            )

        return response.content
    except Exception as exc:
        logger.error(
            "LLM call failed (org=%s, task_type=%s, task=%s): %s",
            resolved_org,
            task_type,
            task_id,
            exc,
        )
        failures = _task_llm_failures.get()
        if failures is not None:
            failures.append(
                {
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "task_type": task_type,
                    "model": model,
                }
            )
        raise LLMCallError(f"LLM call failed: {exc}") from exc
