# Hermes Integration — Operations Runbook

This document covers every remaining operational step required to bring the Hermes Agent parity features into a live production environment. All code changes have already been merged to `main`; what follows is strictly infra provisioning and secret management.

---

## 1. Apply Kubernetes Infrastructure

All manifests live in `infra/k8s/hermes/`.

```bash
# Apply the full Hermes overlay (PVCs + Secret template)
kubectl apply -k infra/k8s/hermes/

# Verify volumes are bound
kubectl get pvc -n autoswarm
# Expected:
#   autoswarm-skills-pvc       Bound   ...
#   autoswarm-edge-memory-pvc  Bound   ...
```

> [!WARNING]
> Both PVCs use `storageClassName: standard`. If your cluster uses a different RWX-capable StorageClass (e.g., `efs-sc` on EKS, `azurefile` on AKS), edit `pvc-skills.yaml` before applying.

---

## 2. Mount Volumes in Deployments

Add the following `volumeMounts` and `volumes` blocks to the **Nexus API** and **Celery worker** Deployments:

```yaml
# In spec.template.spec.containers[*]:
volumeMounts:
  - name: autoswarm-skills
    mountPath: /var/lib/autoswarm/skills
  - name: autoswarm-edge-memory
    mountPath: /var/lib/autoswarm         # SQLite db lives here

# In spec.template.spec:
volumes:
  - name: autoswarm-skills
    persistentVolumeClaim:
      claimName: autoswarm-skills-pvc
  - name: autoswarm-edge-memory
    persistentVolumeClaim:
      claimName: autoswarm-edge-memory-pvc
```

> [!NOTE]
> `autoswarm-edge-memory-pvc` is `ReadWriteOnce` — mount it **only on the Nexus API pod** (single writer). Celery workers only need `autoswarm-skills-pvc` (`ReadWriteMany`).

---

## 3. Populate Secrets

The `secret-hermes.yaml` file contains **placeholder** base64 values. Replace them before applying, or better yet, use Sealed Secrets / External Secrets Operator.

### Option A — Manual (dev/staging only)
```bash
kubectl create secret generic autoswarm-hermes-secrets -n autoswarm \
  --from-literal=TELEGRAM_BOT_TOKEN="<token from @BotFather>" \
  --from-literal=TELEGRAM_WEBHOOK_SECRET="$(openssl rand -hex 32)" \
  --from-literal=DISCORD_WEBHOOK_SECRET="$(openssl rand -hex 32)" \
  --from-literal=TAVILY_API_KEY="<from app.tavily.com>" \
  --from-literal=GITHUB_TOKEN="<fine-grained PAT, read:repo scope>" \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Option B — Sealed Secrets (recommended for production)
```bash
# Encrypt each literal into a SealedSecret
kubeseal --fetch-cert --controller-namespace=kube-system > pub-cert.pem

kubectl create secret generic autoswarm-hermes-secrets -n autoswarm \
  --from-literal=TELEGRAM_BOT_TOKEN="..." \
  --dry-run=client -o yaml \
  | kubeseal --cert pub-cert.pem -o yaml > infra/k8s/hermes/sealed-secret-hermes.yaml

kubectl apply -f infra/k8s/hermes/sealed-secret-hermes.yaml
```

---

## 4. Register Gateway Webhooks

### Telegram
1. Open a chat with [@BotFather](https://t.me/botfather) and create a bot → copy the token.
2. Set the webhook URL pointing to your production Nexus API:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://api.autoswarm.yourdomain.com/api/v1/gateway/telegram/webhook"}'
```
3. Optionally set a `secret_token` for payload verification:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d '{"url": "...", "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"}'
```

### Discord
1. Go to [Discord Developer Portal](https://discord.com/developers/applications) → your app → Interactions Endpoint URL.
2. Set it to: `https://api.autoswarm.yourdomain.com/api/v1/gateway/discord/webhook`
3. For slash command triggering (`/initiate_acp`), register the command:
```bash
curl -X POST "https://discord.com/api/v10/applications/<APP_ID>/commands" \
  -H "Authorization: Bot <BOT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name":"initiate_acp","description":"Trigger an ACP run","options":[{"name":"url","description":"Target URL","type":3,"required":true}]}'
```

---

## 5. Configure MCP Tool Servers

The Phase I Analyst bootstraps MCP servers using `packages/workflows/mcp_config.json`. Ensure the following environment variables are available inside the Celery worker container:

| Variable | Source | Purpose |
|---|---|---|
| `TAVILY_API_KEY` | `autoswarm-hermes-secrets` | Tavily web-search MCP server |
| `GITHUB_TOKEN` | `autoswarm-hermes-secrets` | GitHub MCP server |
| `AUTOSWARM_SKILLS_DIR` | ConfigMap or env | Override default skills PVC path |

Reference these from the Deployment `envFrom`:
```yaml
envFrom:
  - secretRef:
      name: autoswarm-hermes-secrets
```

---

## 6. Verify the Integration

```bash
# 1. Check the skills volume is writable from the Celery worker
kubectl exec -n autoswarm deploy/autoswarm-celery -it -- \
  ls /var/lib/autoswarm/skills

# 2. Trigger a test ACP run and confirm a skill file appears
curl -X POST https://api.autoswarm.yourdomain.com/api/v1/acp/initiate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"target_url": "https://example.com", "description": "parity smoke test"}'

# 3. Validate FTS5 edge memory is recording transcripts
kubectl exec -n autoswarm deploy/autoswarm-nexus-api -it -- \
  python -c "
from nexus_api.memory_store.db import memory_store
results = memory_store.fts_search('smoke test')
print(f'FTS hits: {len(results)}')
"

# 4. Confirm gateway is reachable
curl -X POST https://api.autoswarm.yourdomain.com/api/v1/gateway/telegram/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":{"text":"/initiate_acp https://example.com"}}'
```

---

## 7. Environment Variable Reference

All new variables are declared in `apps/nexus-api/nexus_api/config.py` and read from the environment or `.env` file at startup.

| Variable | Default | Required in Prod? | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `""` | ✅ if using Telegram | Bot token from @BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | ✅ | HMAC secret for Telegram payload validation |
| `DISCORD_WEBHOOK_SECRET` | `""` | ✅ if using Discord | HMAC secret for Discord payload validation |
| `TAVILY_API_KEY` | `""` | ✅ for MCP web search | From app.tavily.com |
| `GITHUB_TOKEN` | `""` | ✅ for MCP GitHub access | Fine-grained PAT |
| `AUTOSWARM_SKILLS_DIR` | `/var/lib/autoswarm/skills` | ✅ | PVC mount path for skill scripts |
| `AUTOSWARM_STATE_DB_PATH` | `/var/lib/autoswarm/autoswarm_state.db` | ✅ | SQLite edge memory location |
