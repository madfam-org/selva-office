"""Shared ModelRouter factory — used by both worker and nexus-api.

Builds a fully-configured ``ModelRouter`` from environment-provided API
keys and an org-config YAML file.  Callers pass their Settings-derived
values rather than reading ``os.environ`` directly, so the function
stays testable and independent of any specific Settings class.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from . import credentials
from .base import InferenceProvider
from .grants import required_providers
from .org_config import OrgConfig, ProviderConfig, load_org_config
from .providers.anthropic import ANTHROPIC_API_URL, AnthropicProvider
from .providers.generic import GenericOpenAIProvider
from .providers.ollama import OllamaProvider
from .providers.openai import OpenAIProvider
from .providers.openrouter import OpenRouterProvider
from .router import ModelRouter

logger = logging.getLogger(__name__)


ENV_ANTHROPIC_TIMEOUT = "ANTHROPIC_TIMEOUT_SECONDS"
DEFAULT_ANTHROPIC_TIMEOUT_SECONDS = 120.0


def _anthropic_timeout_seconds() -> float:
    """Read timeout for Anthropic calls (``ANTHROPIC_TIMEOUT_SECONDS``).

    A non-streaming Messages call sends no bytes until the whole answer is
    generated, so long outputs (and adaptive thinking) need more than the
    120 s default or they die as an empty ``ReadTimeout``. Invalid or
    non-positive values fall back to the default.
    """
    raw = os.environ.get(ENV_ANTHROPIC_TIMEOUT, "").strip()
    if not raw:
        return DEFAULT_ANTHROPIC_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r", ENV_ANTHROPIC_TIMEOUT, raw)
        return DEFAULT_ANTHROPIC_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_ANTHROPIC_TIMEOUT_SECONDS


def _resolve_api_key(env_name: str) -> str | None:
    import os

    return os.environ.get(env_name)


def _build_extra_anthropic(name: str, cfg: ProviderConfig) -> InferenceProvider | None:
    """An extra Anthropic account from the org config, or None (logged).

    Fail closed (``madfam_inference.credentials``): the name must be
    ``anthropic-<suffix>``, the adapter must be the native one, and the name
    must be in ``PROVIDER_GRANTS_REQUIRED_FOR`` so the account can only ever
    spend under a grant of its own. An absent key just means "not registered".
    """
    if cfg.adapter != "anthropic" or not credentials.valid_credential_name(name):
        logger.error(
            "org config provider %r is NOT registered: an extra Anthropic account "
            "needs a name of the form anthropic-<suffix> and adapter: anthropic",
            name,
        )
        return None
    if name not in required_providers():
        logger.error(
            "org config provider %r is NOT registered: an extra Anthropic account "
            "must be listed in PROVIDER_GRANTS_REQUIRED_FOR (fail closed)",
            name,
        )
        return None
    api_key = _resolve_api_key(cfg.api_key_env) or ""
    if not api_key:
        logger.info("org config provider %r not registered: %s is not set", name,
                    cfg.api_key_env)
        return None
    logger.info("org config provider %r registered (native Anthropic adapter, key from %s)",
                name, cfg.api_key_env)
    return AnthropicProvider(
        api_key=api_key,
        timeout=_anthropic_timeout_seconds(),
        provider_name=name,
        credential_env=cfg.api_key_env,
        base_url=cfg.base_url or ANTHROPIC_API_URL,
    )


def build_router_from_env(
    org_config_path: str = "~/.selva/org-config.yaml",
    *,
    anthropic_api_key: str | None = None,
    openai_api_key: str | None = None,
    openrouter_api_key: str | None = None,
    together_api_key: str | None = None,
    fireworks_api_key: str | None = None,
    deepinfra_api_key: str | None = None,
    siliconflow_api_key: str | None = None,
    moonshot_api_key: str | None = None,
    groq_api_key: str | None = None,
    mistral_api_key: str | None = None,
    ollama_base_url: str = "http://localhost:11434",
) -> ModelRouter:
    """Build a ``ModelRouter`` with all available providers.

    This is the single source of truth for provider registration.
    Both the worker and nexus-api inference proxy call this function.
    """
    try:
        org_config = load_org_config(Path(org_config_path).expanduser())
    except (FileNotFoundError, OSError):
        logger.warning(
            "Org config not found at %s — using default provider routing",
            org_config_path,
        )
        org_config = OrgConfig()

    providers: dict[str, InferenceProvider] = {}

    if anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(
            api_key=anthropic_api_key, timeout=_anthropic_timeout_seconds()
        )
    if openai_api_key:
        providers["openai"] = OpenAIProvider(api_key=openai_api_key)
    if openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(api_key=openrouter_api_key)
    if together_api_key:
        providers["together"] = GenericOpenAIProvider(
            base_url="https://api.together.xyz/v1",
            api_key=together_api_key,
            model="meta-llama/Llama-3.3-70B-Instruct",
            provider_name="together",
        )
    if fireworks_api_key:
        providers["fireworks"] = GenericOpenAIProvider(
            base_url="https://api.fireworks.ai/inference/v1",
            api_key=fireworks_api_key,
            model="accounts/fireworks/models/llama-v3p1-70b-instruct",
            provider_name="fireworks",
        )
    if deepinfra_api_key:
        providers["deepinfra"] = GenericOpenAIProvider(
            base_url="https://api.deepinfra.com/v1/openai",
            api_key=deepinfra_api_key,
            model="meta-llama/Llama-3.3-70B-Instruct",
            provider_name="deepinfra",
        )
    if siliconflow_api_key:
        providers["siliconflow"] = GenericOpenAIProvider(
            base_url="https://api.siliconflow.cn/v1",
            api_key=siliconflow_api_key,
            model="THUDM/GLM-5",
            provider_name="siliconflow",
        )
    if moonshot_api_key:
        providers["moonshot"] = GenericOpenAIProvider(
            base_url="https://api.moonshot.cn/v1",
            api_key=moonshot_api_key,
            model="kimi-k2.5",
            provider_name="moonshot",
        )
    if groq_api_key:
        providers["groq"] = GenericOpenAIProvider(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_api_key,
            model="llama-3.3-70b-versatile",
            provider_name="groq",
        )
    if mistral_api_key:
        providers["mistral"] = GenericOpenAIProvider(
            base_url="https://api.mistral.ai/v1",
            api_key=mistral_api_key,
            model="mistral-large-latest",
            provider_name="mistral",
            vision=True,
        )

    # Register additional providers from org config (skip already registered).
    for name, cfg in org_config.providers.items():
        if name in providers:
            continue
        if cfg.adapter == "anthropic" or credentials.is_extra_credential(name):
            extra = _build_extra_anthropic(name, cfg)
            if extra is not None:
                providers[name] = extra
            continue
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

    # Always include Ollama as local fallback.
    providers["ollama"] = OllamaProvider(base_url=ollama_base_url)

    return ModelRouter(providers=providers, org_config=org_config)
