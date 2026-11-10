# Inference usage → Dhanam's cost ledger (`cost.event.v1`, source `selva`)

Last updated: 2026-11-10

Dhanam owns MADFAM's ecosystem cost ledger. Every source pushes the same
`cost.event.v1` contract to Dhanam's `POST /v1/cost-events` with its own Janua
machine client. This is Selva's side: a sweep that rolls `compute_token_ledger`
up into daily inference events.

**State: dormant.** The CronJob is suspended, `SELVA_COST_EVENTS_EMIT_ENABLED` is
`false`, and no client pair exists yet. The dry run works today.

- Code: `apps/nexus-api/nexus_api/cost_events/`
- Table: `cost_event_outbox` (migration `0043`)
- Schedule: `infra/k8s/production/cost-events-cronjob.yaml` (hourly, suspended)
- Tests: `tests/unit/test_selva_cost_events_rollup.py`, `tests/unit/test_selva_cost_events_sweep.py`

## What one sweep does

1. **Window.** It reads the last `SELVA_COST_EVENTS_LOOKBACK_DAYS` (default 7)
   CLOSED civil days in America/Mexico_City. Today is never built.
2. **Read.** It reads `compute_token_ledger` through `tenant_session("platform")`.
   - The strict RLS policies honour the `platform` marker, so the sweep sees every
     org on the regular pool.
   - Production sets no `DATABASE_ADMIN_URL`, so `admin_session()` would see zero
     rows.
3. **Classify and roll up.** See the next section. Rows without a provider (dispatch
   budget debits) are not inference and are skipped.
4. **Sync the outbox.** New groups become `pending` rows; a changed group gets its
   new payload and goes back to `pending`.
   - A group that disappeared is sent again as `status: cancelled` when Dhanam
     already holds it. Otherwise its row is deleted.
5. **Send.** It posts due `pending` rows in batches of up to 500, with a Janua
   `client_credentials` token (scope `dhanam-cost-events:write`, audience
   `dhanam-api`).

It prints one JSON line of counts and codes: no org, no amount, no payload.

## Who paid (ruling C13)

`cost_usd` on a ledger row is a **list-price estimate** from
`madfam_budget_gate.cost_model`, never an invoice. Each row with a provider is
one of the following.

| Funding | Rule | Event |
|---|---|---|
| `local` | The provider is in `SELVA_COST_EVENTS_LOCAL_PROVIDERS` (default `ollama`). | **None.** Its cost is cluster compute (Waybill), not tokens. The cost model prices these rows at its high fallback rate, so their `cost_usd` means nothing. Counted as `withheld_tokens.local_compute`. |
| `grant` | A declared provider credit grant covers the row. That is the grant guard's own test: same provider, the call's time inside `[starts_at, expires_at)`, and the org allowed (with the platform alias). | A **non-cash memo outside COGS**. It is sent only when Dhanam accepts `funding` (feature `funding_memo`, below), with `cost_class: opex`. Until then it is withheld as `grant_memo_unsupported`. |
| `funding_unknown` | The provider may only run under a grant (`PROVIDER_GRANTS_REQUIRED_FOR`, or an extra account `anthropic-*`), but no declared grant covers the row. The grants file is missing, or was edited after the fact. | **None, loudly** (`withheld_events.funding_unknown`). Guessing "paid" would book a grant as cash. |
| `paid` | Everything else: MADFAM's own provider key, billed by the provider. | A cost event. |

An invalid grants file stops the sweep with exit code 2; it never falls back to
"no grants".

### Cost class (RFC 0050 D3)

| Paid usage | Class |
|---|---|
| The org has an engagement (`SELVA_COST_EVENTS_ENGAGEMENT_BY_ORG`) | `cogs` |
| The caller maps to a client-facing product (`SELVA_COST_EVENTS_PRODUCT_BY_CALLER`) | `cogs` |
| The org is a Selva tenant other than MADFAM (Selva is the product) | `cogs`, product `selva` |
| MADFAM's own unattributed usage | `opex`: shared platform overhead stays OpEx until Waybill allocation exists (C13) |

MADFAM's own org ids are `PLATFORM_ORG_ID`, `madfam`, `platform` (proxy calls
without an org), `default` (worker debits without an org), and any listed in
`SELVA_COST_EVENTS_PLATFORM_ORGS`.

### Why every event is `basis: estimate`

Dhanam stores `estimate` events and never counts them. That is deliberate:

- The provider's invoice already reaches Dhanam as a card or bank payment.
- Counting Selva's list-price estimate as well would count the same spend twice
  on accrual, and would book a price-table figure instead of the invoice.

The events give the ledger the per-day, per-org, per-product split of that
spend. Turning the split into counted COGS needs contract change 2 below.

## The event

One event per civil day × org × product × engagement × provider × funding:

```json
{
  "schema": "cost.event.v1",
  "id": "selva:inference:20261109:<24 hex>",
  "source": "selva",
  "kind": "inference",
  "occurred_at": "2026-11-09T23:59:59-06:00",
  "amount_minor": 1234,
  "currency": "USD",
  "cost_class": "cogs",
  "basis": "estimate",
  "quantity": "182000",
  "unit": "token",
  "item": { "description": "LLM inference via deepinfra: 41 calls, list-price estimate" },
  "attribution": { "client_ref": "selva-org:<org id>", "engagement": "eng:<slug>" }
}
```

- **`id`** is the SHA-256 of org, product, engagement, provider and funding. The
  same group keeps the same `(source, id)` forever, so a replay is `unchanged` and
  a late row is `updated`.
- **`amount_minor`** is in USD cents, rounded half up. A group under one cent is
  withheld as `below_one_cent`. Rows without `cost_usd` are counted as `unpriced`,
  never guessed.
- **No `fx`.** Dhanam stores its own USD→MXN rate for the civil date (C9).
- **`attribution.product`** is sent only with feature `attribution_product`
  (contract v1.1, dhanam#944). Contract v1.0 refuses unknown fields.
- **`client_ref`** is the Selva org id, an opaque reference. An id over 116
  characters becomes `selva-org-sha256:<40 hex>`.

## Dhanam contract status

- **Source `selva`** is already accepted by contract v1.0, and so is kind
  `inference`. No change is needed for either.
- **Writer grant.** Dhanam needs a `CostEventWriterGrant` for this client and
  source `selva`.

**Contract change 1 (proposed): `funding`.** C13 needs a field that neither v1.0
nor v1.1 has. The proposal, to fold into dhanam#944 or a follow-up:

- Add an optional top-level `funding`: `cash` (the default when absent) or
  `grant`.
- A `grant` event is stored and listed, but never counts toward costs, COGS,
  `event_costs` or `event_count`, whatever its basis or class.
- Ledger rows add `non_cash_memo` (per currency) with the memo total.

Selva sends `funding` only when `SELVA_COST_EVENTS_CONTRACT_FEATURES` includes
`funding_memo`, which must happen after Dhanam deploys it.

**Contract change 2 (later): inference `allocates`.** This is the v1.1 labor
pattern applied to inference:

- An `actual` inference event splits a provider payment (by `transaction_id`)
  across engagements and products in proportion to Selva's estimates.
- Each peso is counted once, as the invoice says.

It needs the provider payments tagged in Dhanam first.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SELVA_COST_EVENTS_EMIT_ENABLED` | off | `true` sends; the dry run never needs it. |
| `SELVA_DHANAM_COST_EVENTS_CLIENT_ID` / `_SECRET` | empty | Janua pair of `selva-dhanam-cost-events`. |
| `JANUA_ISSUER_URL`, `DHANAM_API_URL`, `PLATFORM_ORG_ID` | from `selva-config` | Token endpoint `{issuer}/api/v1/oauth/token`; events `{dhanam}/v1/cost-events`. |
| `SELVA_COST_EVENTS_LOOKBACK_DAYS` | 7 | Closed days rebuilt per sweep (1–62). |
| `SELVA_COST_EVENTS_START_DATE` | none | No day before it is built. |
| `SELVA_COST_EVENTS_CONTRACT_FEATURES` | empty (v1.0) | `attribution_product`, `funding_memo`. |
| `SELVA_COST_EVENTS_LOCAL_PROVIDERS` | `ollama` | Providers on MADFAM's own compute. |
| `SELVA_COST_EVENTS_PRODUCT_BY_CALLER` | `{}` | JSON `{caller: product}` for client-facing products. |
| `SELVA_COST_EVENTS_ENGAGEMENT_BY_ORG` | `{}` | JSON `{org_id: engagement}` (RFC 0050 D6). |
| `SELVA_COST_EVENTS_PLATFORM_ORGS` | empty | Extra org ids that mean MADFAM. |

A malformed value stops the command with exit code 2 and names the variable,
never its value.

## Operating it

```bash
python -m nexus_api.cost_events --dry-run                     # counts only, writes nothing
python -m nexus_api.cost_events --dry-run --since 2026-10-01  # backfill preview
python -m nexus_api.cost_events                               # one real sweep
python -m nexus_api.cost_events --since 2026-10-01 --until 2026-10-31 --replay
```

Exit codes:

- **0**: done.
- **1**: an operator problem. One of: Dhanam 403 (no writer grant for source
  `selva`), 409 (an id belongs to another space), 401 twice (audience, org
  binding or key rotation), or an unexpected status.
- **2**: refused to run (flag off, configuration missing or malformed).

How each answer is handled:

- **Transient** (429, 5xx, network, Janua down): the batch is backed off (1, 2,
  4 … minutes, at most 6 h) and retried by a later sweep. Not an alert.
- **400**: only the refused events become `rejected`, with error codes (the
  field names). The rest go out in the next batch. A refused event is retried
  when its payload changes, or with `--replay`.

Metrics (`selva_cost_events_*`: built, withheld, outbox changes, sent,
pending, last success) are registered in the process that runs the sweep. The
scheduled sweep is a short-lived Job, so its durable signals are the summary
line and the Job's failure.

## Turning it on (owner)

1. **Identity.** Janua client `selva-dhanam-cost-events` (enclii platform, below),
   then `enclii --profile admin secrets provision oidc --platform selva-dhanam-cost-events --intake-profile default`.
2. **Writer grant.** Dhanam `provision-cost-event-writer-grant`: this client id,
   its organization, the company space, source `selva`.
3. **Secret.** Move `optional/dhanam-cost-events-external-secret.yaml` into
   `kustomization.yaml` (a PR).
4. **Dry run.** Run it in a nexus-api pod and read the counts, especially
   `withheld_events.funding_unknown`, which should be 0.
5. **Switch on.** Set `SELVA_COST_EVENTS_EMIT_ENABLED: "true"` and
   `suspend: false` in `cost-events-cronjob.yaml` (a PR).
6. **Later.** Add `funding_memo` and `attribution_product` to
   `SELVA_COST_EVENTS_CONTRACT_FEATURES` once Dhanam deploys them.

### enclii registry entries (to add in the enclii repo)

`config/ecosystem-oidc-provision.yaml` (and its CLI copy):

```yaml
  selva-dhanam-cost-events:
    intake_target: selva/dhanam-cost-events-client
    intake_key_map:
      dhanam_cost_events_client_id: client_id
      dhanam_cost_events_client_secret: client_secret
    janua_client:
      name: selva-dhanam-cost-events
      client_key: selva-dhanam-cost-events
      audience: dhanam-api
      is_confidential: true
      organization_id: <madfam-ecosystem org, as for the other cost-event writers>
      allowed_scopes: [dhanam-cost-events:write]
      grant_types: [client_credentials]
```

`apps/switchyard-api/internal/secretsintake/registry.yaml`:

```yaml
  selva/dhanam-cost-events-client:
    vault_path: secret/selva
    namespace: selva
    external_secret: selva-dhanam-cost-events
    keys: [dhanam_cost_events_client_id, dhanam_cost_events_client_secret]
    generate:
      disabled: true
```

This is distinct from the `selva/dhanam-cogs-client` READ client
(`dhanam-cogs:read`) for the MCP. Never widen one into the other.
