# Provider credit grants

Selva can be told that it holds prepaid credit with an inference provider
(an amount, a window, and which orgs may draw on it), meter that credit in
real time, and stop using the provider the moment the credit is dead. Code:
`packages/inference/madfam_inference/grants.py`. Hook: `ModelRouter` in
`packages/inference/madfam_inference/router.py`.

This repo is public. The real grant (amount, dates, org ids) lives only in
Vault. Every number below is a placeholder.

## Declaring a grant

The grant is Vault KV `secret/selva` property `provider_grants_json`, synced
by the ExternalSecret `selva-provider-grants`
(`infra/k8s/production/provider-grants-external-secret.yaml`) to the file
`/etc/selva/provider-grants/provider-grants.json` (`PROVIDER_GRANTS_PATH`).

The provider key is NOT part of the grant. `ANTHROPIC_API_KEY` comes from the
existing Kubernetes Secret `selva-llm-secrets` (provisioned outside this repo,
like `DEEPINFRA_API_KEY`) and is mounted `optional: true` on inference-gateway,
nexus-api and workers. That is safe on its own: with
`PROVIDER_GRANTS_REQUIRED_FOR=anthropic` and no valid grant, Anthropic is
registered but never used.

`provider_grants_json` (JSON, or YAML; validated strictly, unknown fields refused):

```json
{"grants": [{
  "id": "example-grant",
  "provider": "anthropic",
  "key_env": "ANTHROPIC_API_KEY",
  "amount_usd": 100.0,
  "safety_margin_usd": 5.0,
  "starts_at": "2030-01-01T00:00:00Z",
  "expires_at": "2030-01-02T00:00:00Z",
  "allowed_orgs": ["madfam"],
  "pacing": "use_it_or_lose_it",
  "autopilot": false,
  "notes": "free text"
}]}
```

- `ceiling = amount_usd - safety_margin_usd`. Spend never passes it.
- Timestamps must carry a timezone. After `expires_at` the grant is dead.
- `allowed_orgs` is matched exactly against the request's org. The platform
  org (`PLATFORM_ORG_ID`, `madfam` in production) and the literal `madfam`
  count as one identity. Add any other alias (a Janua org UUID, or `platform`
  for gateway calls that send no `X-Selva-Tenant-Org`) to the list.
- Local/dev alternative: env `PROVIDER_GRANTS_JSON` with the same document.
  The file wins when both are set.

Other env:

| Env | Default | Meaning |
|---|---|---|
| `PROVIDER_GRANTS_PATH` | unset | Grants file (production: the path above). |
| `PROVIDER_GRANTS_REQUIRED_FOR` | unset | Comma list of providers that may ONLY run under a grant (production: `anthropic`). |
| `PROVIDER_GRANTS_REDIS_URL` | `REDIS_URL` | Meter Redis. |
| `PROVIDER_GRANTS_RESERVATION_TTL_SECONDS` | `150` | How long an in-flight hold lives if its pod dies. Keep it above the provider read timeout: production workers set `660` with `ANTHROPIC_TIMEOUT_SECONDS=600`. |

## Several accounts for one vendor

Selva can hold more than one Anthropic account. Each extra account is its own
provider named `anthropic-<suffix>`, declared in the org config with the
native adapter (code: `packages/inference/madfam_inference/credentials.py`):

```yaml
providers:
  anthropic-example:
    adapter: anthropic          # native Messages adapter, not the OpenAI-compatible path
    api_key_env: ANTHROPIC_API_KEY_EXAMPLE
```

- The built-in `anthropic` provider (`ANTHROPIC_API_KEY`) is unchanged.
- An extra account is registered only when its key env var is set AND its name
  is in `PROVIDER_GRANTS_REQUIRED_FOR`. Otherwise it is not registered (logged
  at ERROR when the list is missing it). The guard re-checks the list per call
  (`not_grant_required`) and the router runs the guard whenever an extra
  account is registered, so an extra account is never used unmetered.
- It spends only under grants whose `provider` is its exact name. The guard
  matches grants by provider name, so two accounts never draw on each other's
  grant: a dead `anthropic` grant does not borrow from `anthropic-example`.
- The grant's `key_env` must name the env var the key came from (or be
  omitted). A grant naming another env var is not used for that account
  (`key_env_mismatch`), so a grant can never meter the wrong account.
- Prices are the `anthropic` rows of the cost model. The USD ledger
  (`compute_token_ledger.provider`) and the grant meter carry the account
  name, so each account's spend is visible on its own.
- It is in no global priority list and no assignment. Only routing that names
  it reaches it: an `org_overrides.<org>` priority list or assignment, or a
  server-set `provider_allowlist` (for example madfam infra operations, which
  prefer an extra account and fall back to `anthropic`). Every other tenant
  routes exactly as before.

A third account is configuration only: an org-config entry, its key in the
`selva-llm-secrets` Secret, its name in `PROVIDER_GRANTS_REQUIRED_FOR` on
inference-gateway, nexus-api and workers, and a grant with that `provider`.

Order matters: add the name to `PROVIDER_GRANTS_REQUIRED_FOR` and deploy
before (or with) the key, and declare its grant in Vault. A grant for an
extra account is accepted by the strict loader today, because `provider` is a
free name; nothing new is added to the grant schema.

## The fail-closed guarantee

A provider in `PROVIDER_GRANTS_REQUIRED_FOR` is used for a call only when ALL hold:
a grant for that provider parses and validates, it has started and not expired,
its `allowed_orgs` contains the request's org (`RoutingPolicy.org_id`), the
cost model is importable, Redis answers, and the call's worst case fits under
the ceiling. Anything else makes the provider unavailable for that call:

- the router continues its normal fallback chain (an org-config assignment
  pointing at the guarded provider is skipped, and its model is not sent to the
  next provider);
- a model the caller pinned (`model` on `/v1`, e.g. `claude-…`) gets HTTP 503
  `provider_grant_unavailable` naming the reason instead of a silent swap;
- the guard only removes options. Sensitivity (`restricted`/`confidential` stay
  local), tenant task exceptions and org assignments keep their precedence.

Reason codes: `no_grant`, `config_invalid`, `org_missing`, `org_not_allowed`,
`not_started`, `expired`, `ceiling_reached`, `meter_unavailable`,
`cost_model_unavailable`, and for extra accounts `not_grant_required` and
`key_env_mismatch`. Config and Redis errors log at ERROR at most once a
minute.

Metering: before each attempt the router atomically reserves the worst case
(estimated input tokens × input price + `max_tokens` × output price, priced by
`madfam_budget_gate.cost_model`) with a Lua script, so concurrent pods cannot
overshoot. After the call it settles the actual USD from usage; on error it
releases; on timeout or a stream with no usage it settles the worst case.
Reservations expire on their own. A cold Redis seeds `spent` from the USD
ledger (`compute_token_ledger`, provider + window) in nexus-api and the gateway;
workers cannot reach the ledger and seed 0 (logged). The guard keeps one
Redis meter per running event loop: an asyncio Redis client is bound to the
loop that created it, and workers run graph code in more than one loop. All
meters share the same Redis keys, so the ceiling holds across them.

With no grant declared and `PROVIDER_GRANTS_REQUIRED_FOR` empty the guard is
inert and routing is unchanged.

## Reading status

Fields (contract C2): `id`, `provider`, `ceiling_usd`, `spent_usd`,
`reserved_usd`, `remaining_usd`, `starts_at`, `expires_at`,
`seconds_to_expiry`, `burn_usd_per_hour_60m`, `required_usd_per_hour`
(remaining ÷ hours left), `pace_status` (`behind | on_pace | ahead | exhausted
| expired`, or `unknown` when the meter is down), `autopilot`, plus `active`
and `meter_ok`.

- API: `GET /api/v1/providers/grants` on nexus-api — `platform` role, or
  `admin` in the platform org. Also returns `required_for`, `config_source`,
  `config_error`.
- Prometheus (nexus-api `/metrics`): `selva_provider_grant_remaining_usd{grant}`,
  `selva_provider_grant_spent_usd{grant}`, `selva_provider_grant_seconds_to_expiry{grant}`.
  The amount series disappear (not zero) while the meter is unreadable.
- Agent tool: `inference_budget_status` (PLATFORM audience only).
- Python: `await madfam_inference.grants.get_grant_statuses()`.

## Reconciling with the provider

The meter prices calls with Selva's cost model; the provider bills what it
actually served. In the first production run the meter read low by a roughly
fixed amount (requests that timed out on the client were still billed) plus a
few percent of drift (worst-case input estimates on very large contexts, cache
writes). Read the provider's usage during the run and, if the meter is low,
raise `safety_margin_usd` in the grant (Vault edit plus a sync; no restart).
If the meter runs high, lower the margin to use the full balance. A job that
reconciles against the provider's cost-report API is a planned follow-up.

## Owner steps

Production operations are Enclii-first (`AGENTS.md`): use the Enclii secret
and rollout operations where they exist; the raw commands below are the
bootstrap / break-glass equivalent, with placeholders only.

1. Write the grant to Vault (keeps the other `secret/selva` properties):
   `vault kv patch secret/selva provider_grants_json=@<grants.json>`
2. Force the sync instead of waiting up to 15 min:
   `kubectl -n selva annotate externalsecret selva-provider-grants force-sync=$(date +%s) --overwrite`
   then check `kubectl -n selva get externalsecret selva-provider-grants` shows `SecretSynced`.
3. Restart the three consumers (the optional volume only appears in pods
   started after the Secret exists; no reloader runs):
   `kubectl -n selva rollout restart deploy/inference-gateway deploy/nexus-api deploy/workers`
4. Verify: `GET /api/v1/providers/grants` lists the grant with `meter_ok: true`;
   the startup log has `provider grants: 1 grant(s) loaded from /etc/selva/provider-grants/provider-grants.json`.

Routing only reaches the provider where the org config assigns it; the grant
is the brake, not the accelerator. Later edits to `provider_grants_json`
reach pods within ~1–2 minutes of the sync without a restart. To stop early,
remove the `provider_grants_json` property (the Secret is deleted and the file
disappears from running pods within minutes), or set `expires_at` to the past.
