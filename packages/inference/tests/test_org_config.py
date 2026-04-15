"""Tests for org config loading and model assignment logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from madfam_inference.org_config import (
    ModelAssignment,
    OrgConfig,
    ProviderConfig,
    TaskType,
    _parse_yaml,
    load_org_config,
)


class TestTaskType:
    """TaskType enum round-trips correctly."""

    def test_all_values(self) -> None:
        expected = {
            "planning", "coding", "fast_coding", "review", "research",
            "crm", "support", "vision", "embedding",
        }
        assert {t.value for t in TaskType} == expected

    def test_from_string(self) -> None:
        assert TaskType("planning") == TaskType.PLANNING
        assert TaskType("fast_coding") == TaskType.FAST_CODING


class TestOrgConfigDefaults:
    """OrgConfig returns sensible defaults when no file is present."""

    def test_default_config(self) -> None:
        cfg = OrgConfig()
        assert cfg.providers == {}
        assert cfg.model_assignments == {}
        assert cfg.cloud_priority is None
        assert cfg.cheapest_priority is None
        assert cfg.agents == []
        assert cfg.embedding_provider == "openai"
        assert cfg.embedding_model == "text-embedding-3-small"


class TestLoadOrgConfig:
    """Test the file-based config loader."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        cfg = load_org_config(tmp_path / "nonexistent.yaml")
        assert isinstance(cfg, OrgConfig)
        assert cfg.providers == {}
        load_org_config.cache_clear()

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        config_file = tmp_path / "org-config.yaml"
        config_file.write_text("""
providers:
  testprov:
    base_url: https://api.test.com/v1
    api_key_env: TEST_API_KEY
    vision: false

model_assignments:
  planning:
    provider: testprov
    model: test-model-1
    max_tokens: 8192
    temperature: 0.5
  coding:
    provider: testprov
    model: test-model-2

cloud_priority:
  - testprov
  - anthropic

embedding_provider: testprov
embedding_model: test-embed-model
""")
        cfg = load_org_config(config_file)

        assert "testprov" in cfg.providers
        assert cfg.providers["testprov"].base_url == "https://api.test.com/v1"
        assert cfg.providers["testprov"].api_key_env == "TEST_API_KEY"
        assert cfg.providers["testprov"].vision is False

        assert TaskType.PLANNING in cfg.model_assignments
        assert cfg.model_assignments[TaskType.PLANNING].model == "test-model-1"
        assert cfg.model_assignments[TaskType.PLANNING].max_tokens == 8192

        assert TaskType.CODING in cfg.model_assignments
        assert cfg.model_assignments[TaskType.CODING].model == "test-model-2"

        assert cfg.cloud_priority == ["testprov", "anthropic"]
        assert cfg.embedding_provider == "testprov"
        assert cfg.embedding_model == "test-embed-model"
        load_org_config.cache_clear()

    def test_invalid_yaml_returns_defaults(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("{{{{invalid yaml")
        cfg = load_org_config(config_file)
        assert isinstance(cfg, OrgConfig)
        load_org_config.cache_clear()

    def test_unknown_task_type_ignored(self, tmp_path: Path) -> None:
        load_org_config.cache_clear()
        config_file = tmp_path / "org.yaml"
        config_file.write_text("""
model_assignments:
  unknown_type:
    provider: test
    model: test
  planning:
    provider: test
    model: test
""")
        cfg = load_org_config(config_file)
        assert TaskType.PLANNING in cfg.model_assignments
        assert len(cfg.model_assignments) == 1  # unknown_type was skipped
        load_org_config.cache_clear()


class TestModelAssignment:
    """ModelAssignment model validation."""

    def test_defaults(self) -> None:
        ma = ModelAssignment(provider="test", model="test-model")
        assert ma.max_tokens == 4096
        assert ma.temperature == 0.7

    def test_custom_values(self) -> None:
        ma = ModelAssignment(
            provider="deepinfra", model="llama-70b",
            max_tokens=8192, temperature=0.3,
        )
        assert ma.provider == "deepinfra"
        assert ma.model == "llama-70b"
        assert ma.max_tokens == 8192
        assert ma.temperature == 0.3


class TestProviderConfig:
    """ProviderConfig model validation."""

    def test_api_key_env_resolution(self) -> None:
        pc = ProviderConfig(
            base_url="https://api.test.com/v1",
            api_key_env="MY_SECRET_KEY",
        )
        assert pc.api_key_env == "MY_SECRET_KEY"
        assert pc.vision is True  # default
        assert pc.timeout == 120.0  # default

    def test_env_var_lookup(self) -> None:
        """Verify that api_key_env is just a reference, not the actual key."""
        pc = ProviderConfig(
            base_url="https://api.test.com/v1",
            api_key_env="SILICONFLOW_API_KEY",
        )
        with patch.dict("os.environ", {"SILICONFLOW_API_KEY": "sk-test-123"}):
            import os
            assert os.environ.get(pc.api_key_env) == "sk-test-123"


class TestParseYaml:
    """Test the YAML dict parser."""

    def test_parse_with_task_types(self) -> None:
        raw = {
            "model_assignments": {
                "planning": {"provider": "a", "model": "b"},
                "coding": {"provider": "c", "model": "d"},
            }
        }
        cfg = _parse_yaml(raw)
        assert TaskType.PLANNING in cfg.model_assignments
        assert TaskType.CODING in cfg.model_assignments

    def test_parse_empty_dict(self) -> None:
        cfg = _parse_yaml({})
        assert isinstance(cfg, OrgConfig)
