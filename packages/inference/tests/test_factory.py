"""Tests for the shared router factory."""

from __future__ import annotations

from pathlib import Path

from madfam_inference.factory import build_router_from_env
from madfam_inference.org_config import load_org_config


class TestBuildRouterFromEnv:
    """build_router_from_env constructs a ModelRouter from API keys."""

    def test_only_ollama_when_no_keys(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        router = build_router_from_env(
            org_config_path=str(tmp_path / "nonexistent.yaml"),
        )
        assert "ollama" in router.available_providers
        assert "anthropic" not in router.available_providers
        load_org_config.cache_clear()

    def test_registers_anthropic(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        router = build_router_from_env(
            org_config_path=str(tmp_path / "nonexistent.yaml"),
            anthropic_api_key="sk-test",
        )
        assert "anthropic" in router.available_providers
        load_org_config.cache_clear()

    def test_registers_deepinfra(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        router = build_router_from_env(
            org_config_path=str(tmp_path / "nonexistent.yaml"),
            deepinfra_api_key="di-test",
        )
        assert "deepinfra" in router.available_providers
        load_org_config.cache_clear()

    def test_registers_groq_and_mistral(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        router = build_router_from_env(
            org_config_path=str(tmp_path / "nonexistent.yaml"),
            groq_api_key="gsk-test",
            mistral_api_key="msk-test",
        )
        assert "groq" in router.available_providers
        assert "mistral" in router.available_providers
        load_org_config.cache_clear()

    def test_registers_all_providers(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        router = build_router_from_env(
            org_config_path=str(tmp_path / "nonexistent.yaml"),
            anthropic_api_key="sk-ant",
            openai_api_key="sk-oai",
            openrouter_api_key="sk-or",
            together_api_key="tk-tog",
            fireworks_api_key="fw-test",
            deepinfra_api_key="di-test",
            siliconflow_api_key="sf-test",
            moonshot_api_key="ms-test",
            groq_api_key="gsk-test",
            mistral_api_key="msk-test",
        )
        names = router.available_providers
        expected = {
            "anthropic", "openai", "openrouter", "together", "fireworks",
            "deepinfra", "siliconflow", "moonshot", "groq", "mistral", "ollama",
        }
        assert expected.issubset(set(names))
        load_org_config.cache_clear()

    def test_loads_org_config_from_yaml(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        config_file = tmp_path / "org.yaml"
        config_file.write_text("""
model_assignments:
  coding:
    provider: anthropic
    model: claude-sonnet-4-20250514
""")
        router = build_router_from_env(
            org_config_path=str(config_file),
            anthropic_api_key="sk-test",
        )
        assert "anthropic" in router.available_providers
        load_org_config.cache_clear()
