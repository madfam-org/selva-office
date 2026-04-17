# Runbook: DeepInfra bridge mode (Anthropic credits paused)

**Purpose:** temporary routing so the autonomous loop and all ecosystem
services can keep operating while the Anthropic account is unfunded.

**Activate only when** Anthropic-primary calls are visibly failing with auth
or quota errors (check `kubectl logs -n autoswarm deploy/nexus-api | grep -i
anthropic` and `GET /api/v1/metrics/dashboard` cost breakdown → anthropic
row non-zero with `provider_error` spikes).

---

## Activate bridge mode

1. Set the DeepInfra API key as a secret. Key is at
   <https://deepinfra.com/dash/api_keys> (sign in with GitHub as
   `innovacionesmadfam@proton.me`).

   ```bash
   enclii secrets set DEEPINFRA_API_KEY=<key> --service nexus-api --secret
   enclii secrets set DEEPINFRA_API_KEY=<key> --service autoswarm-workers --secret
   ```

   If the CLI is unavailable, fall back to the kubectl form in
   `infra/k8s/production/deepinfra-secret.yaml.example`.

2. Apply the bridge ConfigMap. **This overwrites the live `autoswarm-org-config`
   ConfigMap** — the default lives in `infra/k8s/production/org-config.yaml`
   and is what you re-apply to revert.

   ```bash
   kubectl apply -f infra/k8s/production/org-config-bridge-deepinfra.yaml
   ```

3. Restart the two services that read the config:

   ```bash
   kubectl rollout restart deployment/nexus-api -n autoswarm
   kubectl rollout restart deployment/autoswarm-workers -n autoswarm
   ```

4. Verify the config took effect:

   ```bash
   kubectl logs -n autoswarm deploy/nexus-api --tail=50 | grep -i "providers:"
   # expect to see deepinfra in the registered providers list

   curl -H "Authorization: Bearer $WORKER_API_TOKEN" \
     https://agents-api.madfam.io/v1/intelligence/config | jq '.model_assignments.crm'
   # expect: {"provider": "deepinfra", "model": "meta-llama/Llama-3.3-70B-Instruct", ...}
   ```

5. Smoke-test the revenue-critical path by dispatching one CRM draft task
   against a disposable test lead, and confirming the email body comes back
   without the `[LLM unavailable` placeholder guard tripping. See the
   `v2.1.1 Autonomous Pipeline Security` section in `CLAUDE.md` — that
   guard will abort email send if the LLM returns the unavailable sentinel.

---

## Revert to primary mode

Once Anthropic is funded:

```bash
kubectl apply -f infra/k8s/production/org-config.yaml
kubectl rollout restart deployment/nexus-api -n autoswarm
kubectl rollout restart deployment/autoswarm-workers -n autoswarm
```

Verify revert with the same `intelligence/config` GET — `crm` should return
to `provider: anthropic, model: claude-haiku-*`.

DeepInfra remains registered as a fallback (it's in both priority lists in
the default config too). You do not need to delete the secret.

---

## What changes under bridge mode

| Task type     | Default (Anthropic)           | Bridge (DeepInfra)                          |
|---------------|-------------------------------|---------------------------------------------|
| planning      | claude-opus-4                 | deepseek-ai/DeepSeek-R1-Distill-Llama-70B   |
| coding        | claude-sonnet-4               | Qwen/Qwen2.5-Coder-32B-Instruct             |
| fast_coding   | (already deepinfra)           | meta-llama/Llama-3.3-70B-Instruct           |
| review        | claude-sonnet-4               | Qwen/Qwen2.5-72B-Instruct                   |
| research      | claude-sonnet-4               | meta-llama/Llama-3.3-70B-Instruct           |
| **crm**       | claude-haiku-4                | **meta-llama/Llama-3.3-70B-Instruct**       |
| support       | claude-haiku-4                | meta-llama/Llama-3.1-8B-Instruct            |
| vision        | claude-sonnet-4               | meta-llama/Llama-3.2-90B-Vision-Instruct    |
| embedding     | openai text-embedding-3-small | **unchanged**                               |

Fallback order in both `cloud_priority` and `cheapest_priority` puts
DeepInfra first, Anthropic last. If DeepInfra itself starts erroring, the
router will try OpenAI → Groq → Together → Fireworks → Mistral → Moonshot →
SiliconFlow → OpenRouter before giving up.

---

## Watchouts during bridge mode

1. **Quality drop on planning / review.** DeepSeek-R1-Distill and Qwen2.5-72B
   are strong open-weight models, but expect a visible gap vs Opus 4 on
   multi-step reasoning and nuanced code review. Treat outputs requiring
   high precision as draft quality.
2. **CRM drip tone.** Llama-3.3-70B drafts tend to be slightly more
   verbose and formal than Claude Haiku. HITL approval (`require_approval: true`,
   financial cap $50/day per CLAUDE.md v2.1.1) still gates every send — if
   tone regresses, the reviewer will catch it before spend.
3. **Context window.** Llama-3.3-70B caps at 128k, Qwen2.5 at 128k — fine
   for CRM and most coding. Planning over very large codebases may hit
   limits that Opus's 200k didn't.
4. **Cost observability.** Token ledger (`compute_token_ledger` table) will
   show provider=`deepinfra` for all bridged traffic. Watch
   `GET /api/v1/metrics/dashboard` cost breakdown to track $19.98 burn rate.
5. **Streaming.** All bridged models support streaming, but if any specific
   model in DeepInfra's catalog is sunset, swap the model string in the
   ConfigMap and rollout-restart. The provider registration itself is stable.
6. **Vision multimodal**. Llama-3.2-90B-Vision accepts images but not video.
   Any `ImageAnalysisTool` requests with video-frame input will need to be
   frame-sampled first (this was already true under Claude).

---

## Rollback to previous commit

If the bridge ConfigMap causes worse issues than the Anthropic outage
(unlikely, but possible):

```bash
kubectl rollout undo deployment/nexus-api -n autoswarm
kubectl rollout undo deployment/autoswarm-workers -n autoswarm
kubectl apply -f infra/k8s/production/org-config.yaml
```

File a Sentry issue tagged `bridge-deepinfra` and ping the on-call.
