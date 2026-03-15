"""Inference helper for LangGraph worker nodes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from autoswarm_inference import InferenceProvider, InferenceRequest, InferenceResponse, ModelRouter
from autoswarm_inference.org_config import load_org_config
from autoswarm_inference.providers.anthropic import AnthropicProvider
from autoswarm_inference.providers.generic import GenericOpenAIProvider
from autoswarm_inference.providers.ollama import OllamaProvider
from autoswarm_inference.providers.openai import OpenAIProvider
from autoswarm_inference.providers.openrouter import OpenRouterProvider
from autoswarm_inference.types import RoutingPolicy, Sensitivity

from .config import get_settings

logger = logging.getLogger(__name__)


def _resolve_api_key(env_name: str) -> str | None:
    """Resolve an API key from an environment variable name."""
    import os

    return os.environ.get(env_name)


def build_model_router() -> ModelRouter:
    """Instantiate a ModelRouter with available providers from config.

    Creates real ``InferenceProvider`` instances for each configured
    API key and always includes Ollama as the local fallback.
    Also registers providers defined in the org config.
    """
    settings = get_settings()
    org_config = load_org_config(Path(settings.org_config_path).expanduser())
    providers: dict[str, InferenceProvider] = {}

    if settings.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(api_key=settings.anthropic_api_key)
    if settings.openai_api_key:
        providers["openai"] = OpenAIProvider(api_key=settings.openai_api_key)
    if settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(api_key=settings.openrouter_api_key)
    if settings.together_api_key:
        providers["together"] = GenericOpenAIProvider(
            base_url="https://api.together.xyz/v1",
            api_key=settings.together_api_key,
            model="meta-llama/Llama-3.3-70B-Instruct",
            provider_name="together",
        )
    if settings.fireworks_api_key:
        providers["fireworks"] = GenericOpenAIProvider(
            base_url="https://api.fireworks.ai/inference/v1",
            api_key=settings.fireworks_api_key,
            model="accounts/fireworks/models/llama-v3p1-70b-instruct",
            provider_name="fireworks",
        )
    if settings.deepinfra_api_key:
        providers["deepinfra"] = GenericOpenAIProvider(
            base_url="https://api.deepinfra.com/v1/openai",
            api_key=settings.deepinfra_api_key,
            model="meta-llama/Llama-3.3-70B-Instruct",
            provider_name="deepinfra",
        )

    # New hardcoded providers
    if settings.siliconflow_api_key:
        providers["siliconflow"] = GenericOpenAIProvider(
            base_url="https://api.siliconflow.cn/v1",
            api_key=settings.siliconflow_api_key,
            model="THUDM/GLM-5",
            provider_name="siliconflow",
        )
    if settings.moonshot_api_key:
        providers["moonshot"] = GenericOpenAIProvider(
            base_url="https://api.moonshot.cn/v1",
            api_key=settings.moonshot_api_key,
            model="kimi-k2.5",
            provider_name="moonshot",
        )

    # Register additional providers from org config (skip already registered).
    for name, cfg in org_config.providers.items():
        if name not in providers:
            api_key = _resolve_api_key(cfg.api_key_env) or ""
            if api_key:
                providers[name] = GenericOpenAIProvider(
                    base_url=cfg.base_url,
                    api_key=api_key,
                    model="default",
                    provider_name=name,
                    vision=cfg.vision,
                    timeout=cfg.timeout,
                )

    # Always include ollama as local provider.
    providers["ollama"] = OllamaProvider(base_url=settings.ollama_base_url)

    return ModelRouter(providers=providers, org_config=org_config)


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
) -> str:
    """Convenience wrapper that calls the LLM and returns content.

    Falls back to a placeholder response if no provider is available or
    the inference call fails for any reason.  This ensures that worker
    graph nodes degrade gracefully when no API keys are configured.

    When a response is received, token usage is metered to the billing
    ledger via the nexus-api internal endpoint.
    """
    try:
        request = InferenceRequest(
            messages=messages,
            system_prompt=system_prompt or None,
            policy=RoutingPolicy(sensitivity=sensitivity, task_type=task_type),
        )
        response: InferenceResponse = await router.complete(request)

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
