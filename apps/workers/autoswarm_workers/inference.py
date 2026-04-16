"""Inference helper for LangGraph worker nodes."""

from __future__ import annotations

import logging
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
    org_id: str = "default",
    response_format: dict[str, Any] | None = None,
) -> str:
    """Convenience wrapper that calls the LLM and returns content.

    Falls back to a placeholder response if no provider is available or
    the inference call fails for any reason.  This ensures that worker
    graph nodes degrade gracefully when no API keys are configured.

    When a response is received, token usage is metered to the billing
    ledger via the nexus-api internal endpoint.
    """
    try:
        import time as _time

        from .event_emitter import emit_event as _emit_llm_event

        _llm_start = _time.monotonic()

        request = InferenceRequest(
            messages=messages,
            system_prompt=system_prompt or None,
            policy=RoutingPolicy(sensitivity=sensitivity, task_type=task_type),
            response_format=response_format,
        )
        response: InferenceResponse = await router.complete(request)

        _llm_elapsed = int((_time.monotonic() - _llm_start) * 1000)
        _total_tokens = (
            (response.usage.get("total_tokens") or 0) if response.usage else 0
        )

        # Emit LLM event for observability
        import contextlib

        from .config import get_settings as _get_llm_settings

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
                org_id=org_id,
            )

        return response.content
    except Exception as exc:
        logger.warning("LLM call failed: %s. Using placeholder response.", exc)
        last_content = messages[-1].get("content", "") if messages else ""
        return (
            f"[LLM unavailable — placeholder response for: "
            f"{last_content[:200]}]"
        )
