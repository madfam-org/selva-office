# RFC 0047: Infra self-healing agents

| | |
|---|---|
| Status | Draft (v1 slice implemented behind a flag, off) |
| Program phase | Autonomous operations (`../AUTONOMOUS_OPERATIONS_PROGRAM.md`) |
| Code | `packages/autoheal` (`selva_autoheal`), `apps/nexus-api/nexus_api/routers/infra_autoheal.py`, `apps/workers/selva_workers/jobs/infra_autoheal.py` |
| Depends on | Provider credit grants (`../PROVIDER_CREDIT_GRANTS.md`); several Anthropic accounts as distinct providers (same doc); Enclii operator contract; angelia Courier (ADR-0010) |

## Hard rule

**v1 never writes to production without a human approval, and in v1 the agent
itself never writes at all.** Every Enclii request it can build is a read or a
dry-run (`"dry_run": true`, set by the toolbox, not by the model). The apply
half of Enclii's plan-hash contract (`dry_run: false`, `reason`,
`idempotency_key`, `expected_plan`) cannot be expressed by the toolbox. A
remedy is a reviewed plan that a human applies. Widening this needs a new RFC
(v2 below), not a config change.

## Context

The platform runs on Enclii (k3s, Argo CD, CloudNativePG, Vault +
ExternalSecrets, Kyverno). Alerts flow from Prometheus to Alertmanager to angelia
Courier and on to Telegram. Courier forwards critical alerts only. Diagnosis is
done by hand.

**The incident this is designed against (2026-10-24).**

- In one project namespace, every CNPG cluster sat in «Instance Status
  Extraction Error: HTTP communication issue». The namespace's default-deny
  NetworkPolicy left `cnpg-system` no way to reach the instances' status port
  (TCP 8000).
- `ops.addons.hibernate` reported success while CNPG recreated the pod.
- Diagnosis went from the cluster phase, to the operator logs, to the
  namespace NetworkPolicies, to the default-deny. The fix is enclii #854:
  - it adds the `<cluster>-operator-ingress` policy, converged at provisioning,
    on refresh, and every 10 minutes by the addon network sweep;
  - hibernate now waits for CNPG's confirmation.
- No alert covered project CNPG clusters at the time. Every CNPG rule in the
  cluster is scoped to the shared `postgres-ha` cluster. See "Gaps".

A good v1 agent produces that diagnosis, with evidence, in minutes, and
proposes the fix. That is the acceptance bar for the slice: the recorded replay
in `packages/autoheal/tests/fixtures/` must yield exactly that diagnosis.

## Decision

### 1. Alert intake: a dedicated Alertmanager receiver, not a Courier fan-out

Alertmanager gets one more route, `continue: true`. It matches only the
allowlisted alert names and goes to a `webhook_config` pointing at nexus-api:
`POST /api/v1/infra/autoheal/alertmanager`, with the bearer
`INFRA_AUTOHEAL_WEBHOOK_SECRET` set in `http_config.authorization`.

Why not fan out from Courier:

- **Grouping and dedup already exist in Alertmanager.** One notification is one
  group, and its `groupKey` is stable for the group's life. The incident key is
  `inc-` plus the first 16 hex digits of `sha256(groupKey)`, so repeat
  notifications land on the same incident with no second grouping layer.
- **Courier filters what the healer needs.** It forwards critical alerts only,
  and that is the right paging policy for humans. The agent may want warnings
  that precede an outage.
- **Separate failure domains.** angelia is itself a workload the agent should
  be able to diagnose. Behind Courier, an angelia outage would blind the healer
  exactly when it is needed.
- **Courier's credential is narrow on purpose.** ADR-0010 says its Alertmanager
  route "can do exactly one thing": page the operator recipient. A fan-out
  would widen that credential.

Cost: one receiver in the Alertmanager config and one secret. Both are owner
steps; neither ships in this RFC's PR.

Intake behaviour (`selva_autoheal.intake`, `store`):

- **Validation.** The payload is checked strictly. Labels and annotations are
  length-capped.
- **Qualification.** The group must be `status: firing`, its `alertname` must
  be in `INFRA_AUTOHEAL_ALERTNAMES`, and its `severity` must be in
  `INFRA_AUTOHEAL_SEVERITIES`. An empty allowlist means nothing qualifies.
- **Decisions:**
  - `queued` for a new incident;
  - `duplicate` for a repeat notification inside the cooldown;
  - `flapping` when the key has had more than N runs today;
  - `daily_limit` when the day already has more than M incidents;
  - `killed` when the kill switch is set (the incident is recorded, not queued);
  - `resolved` when the group's status is resolved (the record is closed).
- **No external calls.** The route calls no model, Enclii or Courier. It writes
  Redis only.

### 2. Toolset: read-only, Enclii read APIs first, explicit allowlist, no secrets

The toolbox is `selva_autoheal.tools`. Doctrine is Enclii-first: no kubectl and
no SSH. Allowed calls:

| Tool | Allowed |
|---|---|
| `enclii_ops_read` (always sent as dry-run) | `inventory/network-policies`, `inventory/topology`, `pods/diagnose`, `pods/logs` (≤300 lines), `apps/status`, `apps/diff`, `jobs/list`, `storage/pvc`, `policy/violations` |
| `enclii_get` | `/v1/projects/<slug>`, `…/services`, `…/addons`, `…/environments`; `/v1/addons/<uuid>` and `…/events`; `/v1/services/<uuid>/status`, `…/health/detailed`, `…/networking`; `/v1/observability/alerts`, `…/health` |
| `enclii_remedy_dry_run` (plan only) | `pods/restart`, `apps/sync` |

Guards:

- Anything else is refused before the network, and the refusal is audited.
- The `secrets` domain, env vars, Vault, tokens, credentials, kubeconfig and
  exec are denied by name, even if a pattern were widened by mistake.
- Query strings and `..` are refused.
- Results are redacted (credential-shaped values and long blobs) and truncated.
  The prompt marks them as untrusted data. The replay fixture plants an
  instruction in the operator log to prove that a request the model makes on
  the strength of it is refused.
- A cluster-wide inventory read is narrowed to the incident's namespace before
  the model sees it.

### 3. Evidence first, then a bounded model loop

The agent is `selva_autoheal.agent`.

1. **Fixed probes, no model call.** It always runs the same probes: pods in the
   namespace; the namespace's NetworkPolicies; the project's addons when a
   project label exists; and, for CNPG-looking alerts, the `cnpg-system`
   operator pod and its last 200 log lines.
2. **Deterministic signatures.** The probe results are matched against
   `selva_autoheal.signatures`. Signature 1 is
   `cnpg-operator-ingress-blocked`:
   - a symptom text in the evidence;
   - a default-deny ingress policy in the namespace;
   - no policy admitting `cnpg-system` to TCP/8000 (or any port).
3. **Bounded model loop.** It has two answers available: call one allowed tool,
   or give the final report (JSON protocol, so any provider works). The final
   report must cite evidence ids. Without a cited, observed item, confidence
   is forced to `low`.

### 4. Remedies are Enclii dry-runs, or a prepare-only PR

- When the remedy is an allowlisted Enclii operation, the agent runs its
  dry-run. It attaches the `plan_hash`, plus the Enclii `audit_id` of the
  dry-run.
- When no Enclii operation exists, the remedy kind is `prepare_only_pr`. The
  CNPG case is one: Enclii has no op that writes NetworkPolicies, and the fix
  is a switchyard reconciler. Anything else is `manual`.
- A remedy outside the plan allowlist is downgraded to `manual` and never sent.

### 5. Human approval channel: Telegram via Courier, with the plan hash

- The report goes to the incident chat through Courier's existing
  `POST /v1/courier/send`. Selva is a producer: it sends the
  `X-Internal-API-Key` producer key, `consent.class: operational`, and
  priority `urgent` for critical alerts.
- The message carries the incident id, cited evidence, the proposed remedy, the
  plan hash and how to apply it ("aplicar en Enclii con ese plan_hash";
  `expected_plan`). It is in Spanish.
- Courier's envelope has no threading today. Messages are tied together by the
  incident id. `reply_to` is built only when
  `INFRA_AUTOHEAL_COURIER_THREADING=true`, after angelia accepts the field
  (see "Gaps").
- In v1, approval *is* the human applying the reviewed plan in Enclii. Selva
  receives no approval and applies nothing.

### 6. Apply only after approval, then verify (v2, not built)

1. The approval is recorded as a Selva HITL approval
   (`/api/v1/approvals`, `approval_notifier`), bound to `(incident, plan_hash)`.
   The approver's identity is Janua's. The Telegram message carries a link,
   never a "reply yes" parser.
2. Selva calls the Enclii apply with `dry_run: false`, `reason`,
   `idempotency_key` and `expected_plan`. It uses a **separate**,
   apply-scoped Enclii credential that the read path never holds. A plan that
   changed returns 409 and the run stops.
3. Verify: re-run the probes and signatures, wait for the alert group's
   `resolved` notification, and post the outcome.

### 7. Budget: per incident and per day, inside the grant

The provider grant is the hard ceiling per credential, and the grant guard
refuses past it. Inside it:

- **Caps.** `INFRA_AUTOHEAL_INCIDENT_CAP_USD` and
  `INFRA_AUTOHEAL_DAILY_CAP_USD` have **no default**. An enabled agent without
  them refuses to run. Each model call is admitted on its *worst case*
  (prompt estimate plus the full `max_tokens`) against both remaining caps,
  then charged its actual cost. The pricing is the same cost model as the
  grant meter.
- **Credentials.** `INFRA_AUTOHEAL_PROVIDERS` lists them in preference order:
  `anthropic-ops` first (its grant funds infra and self-healing), then
  `anthropic` (re-funding its grant later is config only). Only credentials
  whose grant is live and has budget are offered to the model client. The
  client sends them as a server-set `provider_allowlist`, so the router falls
  back across them and the guard still checks each one against its own grant.
- **No credential has budget: «sin presupuesto».** The default
  (`INFRA_AUTOHEAL_NO_BUDGET=stop`) posts an evidence-only report, with any
  signature diagnosis, and calls no key. `fallback` runs the reasoning on
  `INFRA_AUTOHEAL_FALLBACK_PROVIDERS` (for example DeepInfra, paid outside any
  grant). That is an owner decision.
- **Ledger.** Spend is metered to `compute_token_ledger` with the incident's
  `task_id`. The `provider` column names the paying credential.

### 8. Stop conditions, loop and flap protection, kill switch, audit

- **Per run:** `max_steps` model calls, `max_seconds`, three unparseable
  replies, the incident or daily cap, a grant refusal («sin presupuesto»), or
  a provider error (`llm_unavailable`).
- **Per key:** a cooldown, and a cap on diagnoses per key per UTC day
  (`flapping`).
- **Global:** a cap on incidents per day. One incident is diagnosed at a time,
  under a Redis lock.
- **Kill switch:** the Redis key `selva:autoheal:kill`. It is checked before
  any read and before every model call. Intake still records incidents but
  queues nothing. `INFRA_AUTOHEAL_ENABLED=false` turns everything off.
- **Audit trail:**
  - a swarm task per incident in the platform org (`infra-autoheal`,
    `incident:<key>`; Review column), holding the incident, the report, every
    tool call including refusals, every model call (provider, model, USD) and
    the delivery result;
  - the Redis incident record (30 days);
  - ledger rows per model call;
  - Enclii's own `audit_logs` row for every request the agent's token makes,
    with the dry-run `audit_id` echoed in the report.

### 9. Widening autonomy

- **v1 (this RFC).** Diagnose and propose; the human applies. Exit criteria:
  - two weeks of reports whose cited evidence holds up on review;
  - no allowlist refusal that turned out to be needed;
  - spend inside the caps.
- **v2.** Approval in Selva HITL, then the agent applies and verifies (§6).
  Every apply is still approved by a human, per plan hash.
- **v3.** Pre-approved low-risk runbooks: named
  `(signature, Enclii op, scope)` triples that the owner approves once, in
  advance, for example "restart a CrashLoopBackOff pod of a stateless service
  after N minutes". Each has:
  - a per-runbook rate limit;
  - a blast-radius bound (one namespace, one pod);
  - automatic verification, with rollback or escalation if verification fails.
  
  Everything else stays v2. Stateful systems (CNPG, PVCs, Vault, ingress,
  NetworkPolicy, Kyverno) never enter v3 without their own RFC.

## Gaps (recorded, not worked around)

1. **No alert covers project CNPG clusters.** The CNPG rules target
   `postgres-ha` only, so on 2026-10-24 nothing would have reached the agent.
   The proposal is a rule per project cluster, `CNPGInstanceStatusUnreachable`
   (`cnpg_collector_up` absent or 0, or the cluster phase not healthy, for
   10 minutes). The replay fixture uses that name. Project clusters may also
   need PodMonitors first.
2. **Enclii has no machine identity and no read-only ops scope.**
   - API token scopes are roles (`admin`, `developer`, `viewer`).
   - A `viewer` token cannot reach `/v1/ops`.
   - Inventory reads need a platform admin.
   
   So v1 needs an admin-scoped token, which *could* write. The toolbox makes
   writes inexpressible, but the credential is broader than the agent. The fix
   belongs in Enclii: an `ops:read` scope (reads plus dry-runs, no apply) for
   a service identity. Recommended before the flag goes on.
3. **Enclii reads Kubernetes Events and CNPG Cluster CRs only partially.**
   - Events are not read at all.
   - The CNPG phase reaches the addon `status_message` only, and the addon
     `status` can say `ready` while the phase is an error.
   
   An `addons/diagnose` read would make the CNPG signature direct.
4. **Courier threading.** The envelope has no `reply_to`. Adding
   `reply_to: {delivery_id}`, resolved by Courier to the provider message id
   it already stores, would thread the report under the first message. That is
   an angelia contract change: madfam-org/angelia#44 (prepare-only). Selva sends
   `reply_to` (a re-diagnosis under the incident's first report) only with
   `INFRA_AUTOHEAL_COURIER_THREADING=true`, after that merges.
5. **Enablement wiring is not in this RFC's PR.**
   - Alertmanager route and secret.
   - `INFRA_AUTOHEAL_*` env on nexus-api and workers.
   - The Enclii token and Courier producer key for Selva.
   - NetworkPolicy: monitoring → nexus-api, and workers → switchyard-api and
     angelia-api.

## Owner decisions needed

1. Which alerts qualify (`INFRA_AUTOHEAL_ALERTNAMES`, severities), and whether
   to add the project-CNPG rule (gap 1).
2. The approval chat (the Courier recipient) and whether the agent gets its
   own producer key.
3. Per-incident and daily caps (private: Vault or the private ops repo, never
   this repo).
4. `stop` or `fallback` when no Anthropic credential has budget.
5. Whether v1 may run with an admin-scoped Enclii token, or waits for an
   `ops:read` scope (gap 2).
6. When to turn `INFRA_AUTOHEAL_ENABLED` on.
