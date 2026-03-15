"""Tests for worker startup validation."""

from __future__ import annotations

import logging
from unittest.mock import patch

from autoswarm_workers.config import Settings


def _make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_validate_providers_warns_with_no_keys(caplog: logging.LogRecord) -> None:
    """validate_providers logs a warning when only Ollama is available."""
    from autoswarm_workers.inference import validate_providers

    mock_settings = _make_settings()
    with (
        patch("autoswarm_workers.inference.get_settings", return_value=mock_settings),
        caplog.at_level(logging.WARNING),
    ):
        validate_providers()

    assert any("No cloud LLM API keys configured" in r.message for r in caplog.records)


def test_validate_providers_logs_available_with_keys(caplog: logging.LogRecord) -> None:
    """validate_providers logs available providers when API keys are set."""
    from autoswarm_workers.inference import validate_providers

    mock_settings = _make_settings(anthropic_api_key="sk-test")
    with (
        patch("autoswarm_workers.inference.get_settings", return_value=mock_settings),
        caplog.at_level(logging.INFO),
    ):
        validate_providers()

    assert any("LLM providers available" in r.message for r in caplog.records)
    assert any("anthropic" in r.message for r in caplog.records)
