# Inference Providers

Reference for LLM inference providers integrated into AutoSwarm, their pricing,
model catalogs, and routing configuration.

*Last updated: 2026-03-14*

## Provider Overview

| Provider | Type | API Format | Default Model | Vision Support |
|----------|------|------------|---------------|----------------|
| Anthropic | Proprietary | Anthropic Messages | claude-sonnet-4-20250514 | Yes |
| OpenAI | Proprietary | OpenAI Chat | gpt-4o | Yes |
| Together AI | Open-source host | OpenAI-compat | Llama-3.3-70B-Instruct | Qwen3-VL |
| Fireworks AI | Open-source host | OpenAI-compat | Llama-3.1-70B-Instruct | Qwen2.5-VL, Llama 4 Vision |
| DeepInfra | Open-source host | OpenAI-compat | Llama-3.3-70B-Instruct | Llama 3.2 Vision, Qwen3-VL |
| OpenRouter | Aggregator | OpenAI-compat | claude-sonnet-4 | Varies by model |
| Ollama | Local | Ollama REST | llama3.2 | Yes (local models) |

## Pricing (per million tokens, Llama 70B class)

| Provider | Input $/M | Output $/M | Notes |
|----------|-----------|------------|-------|
| DeepInfra | $0.23 | $0.40 | Cheapest per-token for 70B |
| Fireworks AI | $0.20 | $0.90 | Cheapest input, higher output (tiered) |
| Together AI | $0.54 | $0.54 | Flat rate, broadest catalog |
| OpenRouter | Varies | Varies | Aggregator markup over underlying provider |
| OpenAI | ~$2.50 | ~$10.00 | GPT-4o pricing (proprietary) |
| Anthropic | ~$3.00 | ~$15.00 | Claude Sonnet 4 pricing (proprietary) |

Pricing as of March 2026. Check provider dashboards for current rates.

## Model Catalog Breadth

| Provider | Available Models | Strengths |
|----------|-----------------|-----------|
| Together AI | 200+ | Broadest open-source catalog, fine-tuning support |
| Fireworks AI | 80+ | Fast inference, function calling, serverless GPUs |
| DeepInfra | 77 | Lowest cost, pay-per-token, no minimum |
| OpenRouter | 100+ | Unified access to multiple providers, fallback routing |

## Selection Rationale

These three open-source providers were selected from a broader evaluation based on:

1. **OpenAI-compatible API**: All three implement the `/v1/chat/completions` endpoint,
   allowing integration via `GenericOpenAIProvider` with zero new provider classes.

2. **Cost efficiency**: DeepInfra and Fireworks offer 70B-class models at 5-10x lower
   cost than proprietary providers. Together provides the broadest catalog at
   competitive rates.

3. **Vision support**: All three host vision-capable open-source models (Llama 3.2
   Vision, Qwen-VL family), enabling multimodal inference without proprietary APIs.

4. **Reliability**: All three have production SLAs, <100ms TTFT for cached models,
   and geographic distribution.

### Alternatives Considered

| Provider | Why Not Selected |
|----------|-----------------|
| Anyscale | Merged into Fireworks AI ecosystem |
| Replicate | Per-second billing model less predictable for batch workloads |
| Groq | Fast but limited model selection, no vision models at evaluation time |
| Perplexity | Focused on search/RAG, not general inference |
| Modal | More of a compute platform than inference API |

## Routing Configuration

### Cloud Priority (Internal sensitivity)

Quality-first ordering for internal/non-sensitive workloads:

```
anthropic > openai > fireworks > together > deepinfra > openrouter
```

### Cheapest Priority (Public sensitivity)

Cost-first ordering for public/non-sensitive workloads:

```
deepinfra > together > fireworks > openrouter > openai > anthropic
```

### Sensitivity Routing

| Sensitivity | Routing Behavior |
|-------------|-----------------|
| `restricted` / `confidential` | Ollama only (local). Fails if unavailable. |
| `internal` | Cloud priority order. Falls through on unavailability. |
| `public` | Cheapest priority order. Falls through on unavailability. |

### Vision Routing

When a request contains multimodal content (`has_media()` returns True), the router
filters candidates to providers where `supports_vision == True` before applying
priority ordering. Falls through to all candidates if no vision providers are
registered.

## Configuration

Set API keys in `.env` to enable each provider:

```bash
# Proprietary
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Open-source (any combination)
TOGETHER_API_KEY=...
FIREWORKS_API_KEY=...
DEEPINFRA_API_KEY=...

# Aggregator
OPENROUTER_API_KEY=sk-or-...

# Local
OLLAMA_BASE_URL=http://localhost:11434
```

Providers without API keys are silently skipped. The router selects from whatever
providers are registered.

## Top Models by Use Case

### Code Generation
| Model | Provider(s) | Notes |
|-------|-------------|-------|
| Claude Sonnet 4 | Anthropic, OpenRouter | Best code quality |
| Llama 3.3 70B Instruct | Together, DeepInfra | Best open-source for code |
| DeepSeek Coder V2 | Together, DeepInfra | Specialized for code |
| Qwen2.5-Coder-32B | Together, Fireworks | Strong coding, smaller footprint |

### Vision / Multimodal
| Model | Provider(s) | Notes |
|-------|-------------|-------|
| GPT-4o | OpenAI | Strongest general vision |
| Claude Sonnet 4 | Anthropic | Strong vision + reasoning |
| Llama 3.2 90B Vision | DeepInfra | Best open-source vision |
| Qwen3-VL | Together, DeepInfra | Competitive open-source vision |
| Qwen2.5-VL | Fireworks | Fast inference, good quality |

### General Reasoning
| Model | Provider(s) | Notes |
|-------|-------------|-------|
| Claude Opus 4 | Anthropic | Highest capability |
| GPT-4o | OpenAI | Strong general purpose |
| Llama 3.3 70B | Together, DeepInfra, Fireworks | Best open-source general |
| Mixtral 8x22B | Together, Fireworks | Good quality/cost ratio |

### Fast / Cheap (Agent inner loops)
| Model | Provider(s) | Notes |
|-------|-------------|-------|
| Llama 3.1 8B | All three OS providers | Sub-cent per call |
| Gemma 2 9B | Together, DeepInfra | Fast, good quality for size |
| Qwen2.5 7B | Together, Fireworks | Strong multilingual |
