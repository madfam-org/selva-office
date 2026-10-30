# A2A v1.0.1-Compatible Surface

Selva exposes an **additive** A2A (Agent-to-Agent) surface that speaks the
**v1.0.1** wire contract, served **alongside** the pre-existing legacy `0.7.0`
surface. It lets an external observability appservice observe and gate Selva's
agents. This surface is **OFF by default** and mounts zero routes until its
feature gate is enabled — the legacy surface is unchanged either way.

- Code: `packages/a2a/selva_a2a/v1.py` (card + JSON-RPC router + state mapping),
  `packages/a2a/selva_a2a/announce.py` (task announcer).
- Wiring: `apps/nexus-api/nexus_api/main.py` (`create_app`, gated block).
- Tests: `packages/a2a/tests/test_a2a_v1.py`,
  `apps/nexus-api/tests/test_a2a_v1_gate.py`.
- Related: [RFC 0018 — A2A external tenant model](./rfcs/0018-a2a-external-tenant-model.md),
  [HITL_FLOW.md](./HITL_FLOW.md).

## Two surfaces, side by side

| | Legacy | v1.0.1 |
|---|---|---|
| Dialect | `0.7.0` | `1.0.1` (`protocolVersion: "/v1.0.1/"`) |
| Agent card | `/api/v1/a2a/.well-known/agent.json` | `/api/v1/a2a/v1/.well-known/agent-card.json` |
| Transport | REST-ish `tasks/send`, `tasks/get`, `tasks/sendSubscribe` | JSON-RPC 2.0 at `/api/v1/a2a/v1/` |
| Task states | `pending`/`running`/`completed`/`failed` | ProtoJSON `TASK_STATE_*` |
| Gate | always mounted (existing behaviour) | `FEATURE_A2A_V1` (default off) |

The legacy surface keeps serving its existing consumers verbatim. Nothing in
the v1 layer changes legacy behaviour.

## The feature gate

The v1 surface is controlled by the same `FEATURE_*` pattern used elsewhere
(`FEATURE_STRIPE_MXN_LIVE`, `FEATURE_VOICE_MODE_LIVE`, ...):

| Env var | Setting | Default | Effect |
|---|---|---|---|
| `FEATURE_A2A_V1` | `settings.feature_a2a_v1` | `false` | When false, the v1 card + JSON-RPC endpoint are **not mounted at all** (404). |
| `A2A_V1_STREAMING` | `settings.a2a_v1_streaming` | `false` | When true (and the gate is on), the SSE `message/stream` method is offered and the card advertises `capabilities.streaming = true`. |

With `FEATURE_A2A_V1=false` the surface is fully inert: the router is never
included, so there is zero behaviour change.

## The wire contract

The v1 layer interoperates with an observer that implements A2A v1.0. Points
marked **choice** were a defensible reading of the spec pending upstream
verification; both sides implement the same choice, and the code marks them
`CHOICE:` in comments so they can be revisited together.

- **Agent card** at `.../v1/.well-known/agent-card.json`: `protocolVersion`
  pinned to `/v1.0.1/`; the v1.0 card shape with an **ordered**
  `supportedInterfaces` list of `{url, protocolBinding}` (JSON-RPC first —
  order is significant); open-string `protocolBinding`; **no** top-level `id`;
  `capabilities.streaming` boolean gating SSE.
- **Task states** (`TaskState`): ProtoJSON SCREAMING_SNAKE_CASE, all nine —
  `TASK_STATE_UNSPECIFIED`, `_SUBMITTED`, `_WORKING`, `_COMPLETED`, `_FAILED`,
  `_CANCELED`, `_REJECTED`, `_INPUT_REQUIRED`, `_AUTH_REQUIRED`. The v0.3
  kebab-case spellings never appear here.
- **JSON-RPC 2.0** over HTTP POST at the versioned endpoint. Methods:
  `message/send`, `message/stream` (SSE, only when `capabilities.streaming`),
  `tasks/get`, `tasks/cancel`. get/cancel params `{"id": "<task id>"}`; Task
  snapshot `{id, status: {state, update}}`; message Parts as proto3-oneof
  objects `{"text"|"data"|"file": ...}`; role `ROLE_USER`; a `tenant` member
  echoed back when present; duplicate terminal snapshots tolerated as a no-op.

## State mapping — which states are reachable today

A2A tasks are bridged into `swarm_tasks` rows. The mapping
(`selva_status_to_task_state` in `v1.py`) is **honest**: it maps only the
states Selva actually reaches and falls back to `TASK_STATE_UNSPECIFIED` for
anything else — it never fabricates an interrupted-state transition.

| Selva `SwarmTask.status` | A2A v1 state | Reachable? |
|---|---|---|
| `pending`, `queued` | `TASK_STATE_SUBMITTED` | ✅ |
| `running` | `TASK_STATE_WORKING` | ✅ |
| `completed` | `TASK_STATE_COMPLETED` | ✅ |
| `failed` | `TASK_STATE_FAILED` | ✅ |
| `cancelled` | `TASK_STATE_CANCELED` | ✅ |
| — | `TASK_STATE_INPUT_REQUIRED` | ❌ not reachable |
| — | `TASK_STATE_AUTH_REQUIRED` | ❌ not reachable |
| — | `TASK_STATE_REJECTED` | ❌ not reachable |
| (unknown status) | `TASK_STATE_UNSPECIFIED` | fallback only |

**Why `INPUT_REQUIRED` and `AUTH_REQUIRED` are not reachable today.** Selva has
exactly one human-pause mechanism: the LangGraph `interrupt()` **approval gate**
(`docs/HITL_FLOW.md`) — an *authorization* gate for privileged actions
(`file_write`, `bash_execute`, `git_push`, `email_send`, `deploy`), which
creates an `ApprovalRequest`. There is:

- **No content-input pause** anywhere — nothing asks a human for more
  information / a clarifying answer. So `INPUT_REQUIRED` has no source.
- **No persisted auth-pause status.** The approval pause is held *inside the
  worker's LangGraph checkpoint*; the worker blocks in
  `interrupt_handler.handle_interrupt` and writes only the terminal
  `completed`/`failed` back to the task record. The row stays `running`
  throughout — no distinct "awaiting authorization" status ever lands on
  `SwarmTask.status`. And per RFC 0018 §2.1, A2A callers are **denied HITL
  approvals** ("no human on the other end"), so an A2A-bridged task cannot enter
  the approval pause at all.

The nine-state enum is fully defined (the surface must advertise the complete
vocabulary) but the mapping only emits the five reachable states plus the
`UNSPECIFIED` fallback. When Selva grows a real human-input or credential pause
point, extend the mapping in `v1.py` — do not add a parallel state machine.

## The task announcer (optional)

A2A defines no server-push of *new* tasks, so the observer exposes its own
intake endpoint that Selva POSTs to when it creates a task. This is opt-in and
independent of the feature gate above.

| Env var | Effect |
|---|---|
| `A2A_OBSERVER_INTAKE_URL` | Absent/blank (default) → announcer **off**, nothing sent. Set → each newly created v1 task is POSTed as `{id, status: {state}, agentCardUrl, [tenant]}`. |
| `A2A_OBSERVER_INTAKE_TOKEN` | Optional bearer token added as `Authorization: Bearer …`. |

The announcer is **fire-and-forget with bounded retry** (3 attempts, jittered
backoff; 4xx is a permanent no-retry reject). It **never blocks or fails the
run** — every transport/HTTP error is logged and swallowed, mirroring
`task_notification_notifier.py`. No platform name appears in code; the intake is
configured purely by these generic env vars.

## Security / operational notes

- The JSON-RPC endpoint sits under `/api/v1/a2a/`, already CSRF-exempt (bearer /
  external-caller surface) in `middleware/csrf.py`.
- Inbound v1 tasks reuse the synthetic `a2a-external` org via `tenant_session`
  (RLS Phase 1.5), exactly like the legacy bridge. RFC 0018 tracks promoting
  each A2A caller to a first-class tenant.
- No secrets are committed; `.env.example` carries only placeholders.
