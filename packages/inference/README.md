# selva-inference

Sensitivity-aware LLM inference routing with multi-provider support. Part of the
[Selva](https://github.com/madfam-org/autoswarm-office) ecosystem.

## Installation

```bash
pip install selva-inference            # core (httpx + pydantic)
pip install selva-inference[openai]    # + OpenAI provider
pip install selva-inference[anthropic] # + Anthropic provider
pip install selva-inference[yaml]      # + org config YAML loading
pip install selva-inference[all]       # everything
```

Within the monorepo (uv workspace):

```bash
uv add selva-inference
```

## Quick Start

```python
from selva_inference import ModelRouter, InferenceRequest, RoutingPolicy, Sensitivity
from selva_inference.providers.openai import OpenAIProvider

router = ModelRouter(providers={
    "openai": OpenAIProvider(api_key="sk-..."),
})

request = InferenceRequest(
    messages=[{"role": "user", "content": "Hello!"}],
    policy=RoutingPolicy(sensitivity=Sensitivity.INTERNAL),
)
response = await router.complete(request)
print(response.content)
```

## Providers

| Provider | Class | Extras | Vision |
|----------|-------|--------|--------|
| Anthropic | `AnthropicProvider` | `[anthropic]` | Yes |
| OpenAI | `OpenAIProvider` | `[openai]` | Yes |
| Ollama (local) | `OllamaProvider` | — | Yes |
| OpenRouter | `OpenRouterProvider` | — | Varies |
| Any OpenAI-compatible | `GenericOpenAIProvider` | — | Configurable |

## Sensitivity Routing

The router selects providers based on data sensitivity:

| Sensitivity | Behavior |
|-------------|----------|
| `restricted` / `confidential` | Local (Ollama) only |
| `internal` | Cloud providers, quality-first ordering |
| `public` | Cloud providers, cost-first ordering |

## Task-Type Routing

Graph nodes can declare a `task_type` to get model-specific routing:

```python
policy = RoutingPolicy(
    sensitivity=Sensitivity.INTERNAL,
    task_type="coding",  # planning | coding | fast_coding | review | research | ...
)
```

The router checks `OrgConfig.model_assignments` for a matching task type. If found,
the assigned provider and model are used. Falls through to priority-list routing
when no assignment matches.

## Org Config

Place a YAML file at `~/.autoswarm/org-config.yaml` (or pass a custom path to
`load_org_config()`). See `data/org-config-template.yaml` for the full schema.

```yaml
providers:
  deepinfra:
    base_url: https://api.deepinfra.com/v1/openai
    api_key_env: DEEPINFRA_API_KEY

model_assignments:
  coding:
    provider: anthropic
    model: claude-sonnet-4-20250514
  fast_coding:
    provider: deepinfra
    model: meta-llama/Llama-3.3-70B-Instruct
```

## Multimodal

Use `MediaContent` for image inputs. The router automatically filters to
vision-capable providers:

```python
from selva_inference import InferenceRequest, MediaContent, ContentType

request = InferenceRequest(
    messages=[{
        "role": "user",
        "content": [
            MediaContent(type=ContentType.TEXT, text="What's in this image?"),
            MediaContent(type=ContentType.IMAGE_URL, url="https://..."),
        ],
    }],
)
```

## Public API

| Export | Module | Description |
|--------|--------|-------------|
| `ModelRouter` | `selva_inference` | Request routing engine |
| `InferenceProvider` | `selva_inference` | Provider ABC |
| `InferenceRequest` | `selva_inference` | Request model |
| `InferenceResponse` | `selva_inference` | Response model |
| `RoutingPolicy` | `selva_inference` | Routing parameters |
| `Sensitivity` | `selva_inference` | Data sensitivity enum |
| `ContentType` | `selva_inference` | Media content type enum |
| `MediaContent` | `selva_inference` | Multimodal content block |
| `OrgConfig` | `selva_inference` | Organization config model |
| `TaskType` | `selva_inference` | LLM task category enum |
| `load_org_config` | `selva_inference` | Config loader (cached) |

## License

AGPL-3.0-only
