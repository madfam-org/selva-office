---
name: incident-triage
description: Respond to a live alert — correlate Prometheus + Loki + Sentry + cluster state, form a root-cause hypothesis, propose and apply the minimum fix, verify the alert clears, and record the incident for post-mortem. Composes prometheus + loki + sentry + cluster-triage tools. Invoked by Alertmanager webhooks AND by human operators pointing the swarm at a fresh incident.
allowed_tools:
  - prom_query
  - prom_query_range
  - prom_alerts_active
  - prom_silence_create
  - loki_query_range
  - loki_labels
  - sentry_issue_list
  - sentry_issue_get
  - sentry_issue_update
  - sentry_event_list_for_issue
  - sentry_breadcrumbs_get
  - k8s_get_pods
  - k8s_describe_pod
  - k8s_get_events
  - k8s_rollout_status
  - argocd_get_app
  - argocd_sync_app
  - argocd_refresh_app
  - grafana_panel_export
  - git_commit
  - git_push
  - github_admin_create_pr
  - save_artifact
metadata:
  category: infrastructure
  complexity: high
  reversibility_cost: medium
---

# Incident Triage Skill

You are the on-call responder. An alert fired, or a human operator just
handed you an incident. Your job is to turn the observability stack into a
single, actionable root-cause narrative and get the affected service back
to green — with a durable record future-you can reach for in a post-mortem.

This skill is deliberately more analytical than `cluster-triage`. That
skill is K8s-centric ("the pod is crashing, get it back up"). This one is
signal-centric: you start from the alert + logs + Sentry trail and decide
*what kind* of incident you're looking at before you touch the cluster.

## Invariants

- **Signals first, actions second.** Every cycle starts with the three
  observability reads (`prom_alerts_active`, `loki_query_range` scoped to
  the alert's time window, `sentry_issue_list` filtered to the affected
  service). Mutations happen only after you've formed a hypothesis.
- **Never silence an alert you don't understand.** `prom_silence_create`
  is reserved for known-transient alerts during planned work — not a way
  to quiet a noisy signal you haven't explained.
- **Resolve Sentry issues only after verification.** `sentry_issue_update
  status="resolved"` is the last step, after you've checked
  `sentry_event_list_for_issue` and confirmed no fresh events landed
  since the fix merged.
- **Escalate to HITL** when the proposed fix touches shared infrastructure
  (database schema, auth secrets, ingress, cloudflare-tunnel). Reversibility
  cost on these is high; the skill caps at `ASK_QUIET` for those categories.

## Runbook — the 7-step incident response loop

### 1. Detect: pull the currently firing alerts

```python
active = await prom_alerts_active(active=True, silenced=False)
```

Read `active.by_severity` first. Critical and high severities drive the
incident's scope. Group by `alertname` to avoid chasing duplicates. Pick
the alert with the earliest `startsAt` that's still active — that's where
the incident began.

### 2. Scope the time window

From the chosen alert's `startsAt`, form a window `[startsAt - 5m, now]`.
This is the frame for every subsequent query. Widen to `-15m` only if the
initial reads return nothing useful.

### 3. Search Loki at the trigger time

```python
logs = await loki_query_range(
    query=f'{{namespace="{ns}", app="{app}"}} |= "ERROR" or "WARN"',
    start=window_start,
    end=window_end,
    limit=500,
)
```

Start broad, then tighten. If `loki_labels()` tells you the service emits
a structured `level` label, prefer `{level="error"}` over the grep-style
`|= "ERROR"`. Collect distinct error messages into a set — a single
novel error message drove most incidents in the 2026-04-* series.

### 4. Find the corresponding Sentry issue

```python
issues = await sentry_issue_list(
    project_slug=<service>, status="unresolved",
    query=f"lastSeen:>{window_start}",
    limit=10,
)
```

Map Loki error signatures to Sentry `shortId`s. If a matching issue
exists, pull breadcrumbs:

```python
bc = await sentry_breadcrumbs_get(issue_id=<id>)
```

The breadcrumb trail almost always reveals the state machine or RPC
sequence that led to the error. This is the Seer-style input for
root-cause hypothesis formation.

### 5. Correlate with cluster state

- `k8s_get_pods(namespace=<ns>, label_selector=f"app={app}")` — are pods
  actually running?
- `k8s_describe_pod` on any non-Ready pod — events + container states
- `argocd_get_app(name=f"{app}-services")` — Synced? Degraded? Drifted
  from git?
- `k8s_rollout_status` on the deployment — is this fallout from a rollout?

### 6. Propose and apply the minimum fix

Map the triangulated signal to one of:

| Pattern | Fix | Tool |
|---|---|---|
| New error class, correlates with recent deploy | Roll back via ArgoCD to previous revision | `argocd_sync_app(name, revision=<prev>)` |
| New error class, NOT tied to a deploy | Open a PR with the code fix | `github_admin_create_pr` + `argocd_refresh_app` once merged |
| Known-transient during planned maintenance | Silence for the window | `prom_silence_create(matchers, duration_minutes, comment)` |
| Kubernetes-level failure (crash loop, image pull) | Delegate to `cluster-triage` skill | (handoff) |
| Data-layer failure (DB connection, migration) | **ESCALATE** — do not auto-fix | HITL |

### 7. Verify + record

- Wait 2–5 minutes (skill time, not wall time — the pod health check +
  alert evaluation interval).
- Re-query: `prom_alerts_active` should no longer list the alert.
  `sentry_event_list_for_issue` should show no new events since the fix.
- Resolve Sentry: `sentry_issue_update(issue_id, status="resolved")`.
- Snapshot the incident graph: `grafana_panel_export` on the key metric's
  panel, PNG embedded in the incident record.
- Write the record to the artifact store: `save_artifact`, key
  `incidents/<incident_id>.yaml`.

## Common incident classes (from recent history)

- **LLM provider exhaustion** (Anthropic $0 credits, 2026-04-16). Signals:
  Sentry `InferenceError: provider returned 401`, Loki `[LLM unavailable`
  in worker logs, Prometheus `rate(inference_errors_total[5m]) > 0`. Fix:
  rotate to fallback provider (Selva proxy routes automatically once the
  router rebuilds) OR top up credits. HITL-gate the credit top-up.
- **Webhook signature failure after secret rotation.** Signals: Sentry
  `401 invalid signature`, Loki bursts at the moment of rotation. Fix:
  re-push the rotated secret via `k8s_secret_write` and trigger a
  rolling restart via `argocd_sync_app`.
- **Database pool exhaustion under burst load.** Signals: Prometheus
  `db_pool_checkout_duration_seconds{quantile="0.99"} > 1`, Sentry
  `OperationalError: remaining connection slots are reserved`. Fix: scale
  up the pool via ConfigMap OR increase HPA max. Consider a burst-queue
  for the originating endpoint.
- **DNS change propagation lag breaking webhook delivery.** Signals:
  external providers 5xx against our webhook endpoint, our service is
  healthy. Silence the alert for the propagation window only if you can
  confirm the DNS record was actually changed and the lag is <1h.

## Output format — the incident record

Every invocation produces:

```yaml
incident_id: <short-uuid>
started_at: <iso8601 — alert's startsAt>
detected_at: <iso8601 — when this skill picked it up>
severity: <critical|warning|info>
alert:
  name: <alertname>
  severity: <from labels>
  summary: <from annotations>
window:
  start: <iso8601>
  end: <iso8601>
signals:
  prometheus: <summary of alert + related metrics>
  loki:
    error_signatures: [<distinct error messages, capped at 10>]
    line_count: <int>
  sentry:
    matching_issue: <shortId or null>
    breadcrumbs_count: <int>
    event_count: <int>
  cluster:
    pods_affected: [<pod names>]
    argocd_status: <Synced|OutOfSync|etc>
root_cause: <concise narrative>
fix_applied: <description>
pr_url: <if applicable>
verification:
  alert_cleared: <bool>
  sentry_resolved: <bool>
  post_fix_event_count: <int>
grafana_panel: <snapshot URL>
escalated_to_hitl: <bool + reason if true>
duration_minutes: <int>
follow_ups:
  - <suggested monitor / tool / skill to prevent recurrence>
```

Write to `incidents/<incident_id>.yaml` via `save_artifact`.
