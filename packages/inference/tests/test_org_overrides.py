"""Per-org model overrides (org-config ``org_overrides``).

Only the named org (or an alias) routes differently. Every other tenant's
routing must be byte-for-byte what it was without the override section.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from madfam_inference.base import InferenceProvider, UsageCallback
from madfam_inference.org_config import OrgConfig, TaskType, _parse_yaml
from madfam_inference.providers.anthropic import AnthropicRefusalError
from madfam_inference.router import ModelRouter
from madfam_inference.types import (
    InferenceRequest,
    InferenceResponse,
    RoutingPolicy,
    Sensitivity,
    StreamUsage,
)

PROD_ORG_CONFIG = (
    Path(__file__).resolve().parents[3] / "infra" / "k8s" / "production" / "org-config.yaml"
)


def _prod_raw() -> dict[str, Any]:
    doc = yaml.safe_load(PROD_ORG_CONFIG.read_text())
    return yaml.safe_load(doc["data"]["org-config.yaml"])


def _config(*, with_overrides: bool = True) -> OrgConfig:
    raw = _prod_raw()
    if not with_overrides:
        raw.pop("org_overrides", None)
    return _parse_yaml(raw)


class _Provider(InferenceProvider):
    def __init__(self, name: str, *, fail: Exception | None = None) -> None:
        self.name = name
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request.policy.model_dump())
        if self.fail is not None:
            raise self.fail
        return InferenceResponse(
            content="ok", model=request.policy.model_override or "default", provider=self.name
        )

    async def stream(
        self, request: InferenceRequest, on_usage: UsageCallback | None = None
    ) -> AsyncIterator[str]:
        self.calls.append(request.policy.model_dump())
        if self.fail is not None:
            raise self.fail
        yield "ok"
        if on_usage is not None:
            on_usage(StreamUsage(input_tokens=1, output_tokens=1))

    async def list_models(self) -> list[str]:
        return []


def _providers(**fail: Exception) -> dict[str, _Provider]:
    return {
        name: _Provider(name, fail=fail.get(name))
        for name in ("anthropic", "deepinfra", "openai", "ollama")
    }


def _req(org: str | None, task_type: str | None, **policy: Any) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "x"}],
        policy=RoutingPolicy(org_id=org, task_type=task_type, **policy),
    )


TASK_TYPES = [t.value for t in TaskType] + [None, "summarization"]
SENSITIVITIES = [Sensitivity.PUBLIC, Sensitivity.INTERNAL]


# ── parsing ────────────────────────────────────────────────────────────────


def test_prod_config_has_madfam_override_per_c4() -> None:
    cfg = _config()
    madfam = cfg.override_for("madfam")
    assert madfam is not None
    opus = {"planning", "coding", "review", "research"}
    sonnet = {"fast_coding", "crm", "support", "vision"}
    for task, assignment in madfam.model_assignments.items():
        assert assignment.provider == "anthropic"
        expected = "claude-opus-5-5" if task.value in opus else "claude-sonnet-5-5"
        assert assignment.model == expected
    assert {t.value for t in madfam.model_assignments} == opus | sonnet
    assert TaskType.EMBEDDING not in madfam.model_assignments
    # DeepInfra stays the global default and the MADFAM fallback.
    assert cfg.cloud_priority == ["deepinfra"]
    assert "deepinfra" in madfam.cloud_priority
    assert all(a.provider == "deepinfra" for a in cfg.model_assignments.values())


def test_aliases_resolve_to_the_same_override() -> None:
    raw = _prod_raw()
    raw["org_overrides"]["madfam"]["aliases"] = ["00000000-0000-0000-0000-000000000001"]
    cfg = _parse_yaml(raw)
    assert cfg.override_for("00000000-0000-0000-0000-000000000001") is cfg.override_for("madfam")
    assert cfg.override_for("someone-else") is None
    assert cfg.override_for(None) is None


def test_invalid_override_is_dropped_and_global_config_survives() -> None:
    raw = _prod_raw()
    raw["org_overrides"]["broken"] = {"model_assignments": {"planning": {"model": "x"}}}
    cfg = _parse_yaml(raw)
    assert cfg.override_for("broken") is None
    assert cfg.override_for("madfam") is not None
    assert len(cfg.model_assignments) == 9


# ── other tenants: byte-for-byte unchanged ─────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("org", [None, "default", "platform", "some-tenant-uuid"])
@pytest.mark.parametrize("task_type", TASK_TYPES)
@pytest.mark.parametrize("sensitivity", SENSITIVITIES)
async def test_non_madfam_routing_is_identical(
    org: str | None, task_type: str | None, sensitivity: Sensitivity
) -> None:
    results = []
    for with_overrides in (False, True):
        providers = _providers()
        router = ModelRouter(providers, org_config=_config(with_overrides=with_overrides))
        request = _req(org, task_type, sensitivity=sensitivity)
        response = await router.complete(copy.deepcopy(request))
        results.append(
            (
                response.provider,
                response.model,
                {n: p.calls for n, p in providers.items()},
                router.allowed_providers_for(request),
            )
        )
    assert results[0] == results[1]
    assert results[0][0] == "deepinfra"


# ── madfam ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_type", "model"),
    [
        ("planning", "claude-opus-5-5"),
        ("coding", "claude-opus-5-5"),
        ("review", "claude-opus-5-5"),
        ("research", "claude-opus-5-5"),
        ("fast_coding", "claude-sonnet-5-5"),
        ("crm", "claude-sonnet-5-5"),
        ("support", "claude-sonnet-5-5"),
        ("vision", "claude-sonnet-5-5"),
    ],
)
async def test_madfam_routes_assigned_tasks_to_anthropic(task_type: str, model: str) -> None:
    router = ModelRouter(_providers(), org_config=_config())
    response = await router.complete(_req("madfam", task_type))
    assert (response.provider, response.model) == ("anthropic", model)


@pytest.mark.asyncio
async def test_madfam_embedding_and_untyped_stay_on_deepinfra() -> None:
    router = ModelRouter(_providers(), org_config=_config())
    emb = await router.complete(_req("madfam", "embedding"))
    assert (emb.provider, emb.model) == ("deepinfra", "BAAI/bge-base-en-v1.5")
    untyped = await router.complete(_req("madfam", None))
    assert untyped.provider == "deepinfra"


@pytest.mark.asyncio
async def test_madfam_falls_back_to_global_deepinfra_assignment() -> None:
    providers = _providers(anthropic=RuntimeError("credit balance too low"))
    router = ModelRouter(providers, org_config=_config())
    response = await router.complete(_req("madfam", "planning"))
    assert response.provider == "deepinfra"
    # DeepInfra gets the GLOBAL planning model and limits, never a claude id.
    call = providers["deepinfra"].calls[-1]
    assert call["model_override"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert call["max_tokens"] == 8192
    assert call["temperature"] == 0.6


@pytest.mark.asyncio
async def test_madfam_without_anthropic_registered_uses_global_assignment() -> None:
    providers = _providers()
    del providers["anthropic"]
    router = ModelRouter(providers, org_config=_config())
    response = await router.complete(_req("madfam", "vision"))
    assert (response.provider, response.model) == (
        "deepinfra",
        "meta-llama/Llama-3.2-90B-Vision-Instruct",
    )


@pytest.mark.asyncio
async def test_madfam_stream_fallback_uses_global_model() -> None:
    providers = _providers(anthropic=RuntimeError("overloaded"))
    router = ModelRouter(providers, org_config=_config())
    chunks = [c async for c in router.stream(_req("madfam", "coding"))]
    assert chunks == ["ok"]
    assert providers["deepinfra"].calls[-1]["model_override"] == (
        "meta-llama/Llama-3.3-70B-Instruct"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitivity", [Sensitivity.RESTRICTED, Sensitivity.CONFIDENTIAL])
async def test_madfam_override_never_beats_sensitivity(sensitivity: Sensitivity) -> None:
    router = ModelRouter(_providers(), org_config=_config())
    response = await router.complete(_req("madfam", "planning", sensitivity=sensitivity))
    assert response.provider == "ollama"


@pytest.mark.asyncio
async def test_refusal_does_not_fall_back_to_another_vendor() -> None:
    providers = _providers(anthropic=AnthropicRefusalError("refused"))
    router = ModelRouter(providers, org_config=_config())
    with pytest.raises(AnthropicRefusalError):
        await router.complete(_req("madfam", "planning"))
    assert providers["deepinfra"].calls == []
