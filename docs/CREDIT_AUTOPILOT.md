# Credit-investment autopilot and MADFAM factory lines

This document explains how MADFAM's own Selva tenant spends a time-boxed
provider credit grant **by itself**. The spend goes to work that makes Selva
better at running the three factory lines: software, geometry and physical
goods, plus Factory-as-a-Product. Every output is a reviewable record. The
autopilot never pushes, sends, posts, or writes to CRM, billing or production
data. The only things it writes are its own task records.

> This repo is public. Grant amounts, balances and dates live only in Vault
> (contract C1, `PROVIDER_GRANTS_JSON`). Nothing in this repo carries them.

## Pieces

| Piece | Where | What it does |
|---|---|---|
| HITL gates | `packages/permissions/selva_permissions/classifier.py` | `generate_quote` maps to PRICING_PROPOSAL and `factory_manifest_publish` maps to FILE_WRITE. Both require approval (ASK) by default. |
| Factory lines | `data/factory-lines/madfam-factory-lines.yaml` | Defines three line departments plus Factory-as-a-Product, with two agents per department. Agents only get read/draft skills. |
| Roster bootstrap | `scripts/seed-madfam-factory-lines.py` | Creates the departments and agents for the platform org if they are missing. It is idempotent. |
| Backlog | `data/credit-investment/backlog.yaml` | Ranked work items. Each item has a `budget_share` of the grant ceiling, the model tiers it allows, and acceptance criteria. A `forbidden_tools` list applies to every item. |
| Policy | `apps/workers/selva_workers/jobs/credit_autopilot_policy.py` | Pure pacing and tier-selection logic, covered by unit tests. |
| Loop | `apps/workers/selva_workers/jobs/credit_autopilot.py` | A worker background job. One replica holds a Redis lock and runs a tick every 3 minutes. |
| Executor | `jobs/credit_autopilot_exec.py`, `jobs/credit_autopilot_bench.py`, `jobs/credit_autopilot_steps.py` | Runs multi-step items: fan-out, refine and benchmark. Enforces each item's budget. |

## Turning it on (platform admin)

1. **Roster.** Run this once against the target environment with a platform-admin token. Re-running it is safe.

   ```bash
   SELVA_API_URL=<nexus-api base URL> SELVA_TOKEN=<platform-admin token> \
     python scripts/seed-madfam-factory-lines.py --org-id <platform org id>
   ```

2. **Grant.** In the Vault grant JSON (contract C1), set the grant to `"autopilot": true`.
3. **Workers.** `CREDIT_AUTOPILOT_ENABLED=true` is set on the workers Deployment (`infra/k8s/production/workers.yaml`). This is key 1 of 2. The loop idles until key 2, the grant's `autopilot` flag, is also set.
4. **Optional tuning.** These env vars adjust the loop:
   - `CREDIT_AUTOPILOT_INTERVAL_SECONDS` (default 180)
   - `CREDIT_AUTOPILOT_MAX_CONCURRENCY` (default 6 items in flight; production sets 8)
   - `CREDIT_AUTOPILOT_FLOOR_USD` (default 2)
   - `CREDIT_AUTOPILOT_MAX_ATTEMPTS` (default 2; production sets 9)
   - `CREDIT_AUTOPILOT_FRONT_LOAD` (default off; production sets `true`): keep starting work while `ahead` of pace. For an expiring grant whose backlog is larger than the ceiling, idling only risks leaving credit unused. The ceiling, floor, expiry cut-off and an unreadable meter still stop new work.
   - `CREDIT_AUTOPILOT_BACKLOG_PATH`

   Workers also set `ANTHROPIC_TIMEOUT_SECONDS=600` (long non-streaming Opus calls send no bytes until they finish) and `PROVIDER_GRANTS_RESERVATION_TTL_SECONDS=660`, so an in-flight call stays counted against the ceiling for its whole life.

   `CREDIT_AUTOPILOT_ORG_ID` may restate the platform org, but if it names any other org the loop refuses to run.

The autopilot needs lane LG's `madfam_inference.grants.get_grant_statuses()`. If that function is missing, the loop logs that it is idle and does nothing.

## How it chooses

On each tick, the loop works through these steps in order:

1. It picks the soonest-expiring live grant that has `autopilot: true`, for the `anthropic` provider.
2. It starts no new work if any of these hold:
   - the pace is `exhausted`, `expired` or `unknown`, or `ahead` without `CREDIT_AUTOPILOT_FRONT_LOAD`;
   - the remaining budget is at or below the floor;
   - expiry is less than 15 minutes away.
3. It frees slots up to `max_concurrency`. A row that is still in flight with no update for 60 minutes counts as a failed attempt.
4. It walks the backlog in rank order. It skips items that are done or in flight, and items that have reached the maximum number of attempts.
5. It picks a model tier for each item from the item's own `tiers`:
   - It starts at the item's preferred tier.
   - When the grant is far behind pace (required burn is more than 2× the burn over the last 60 minutes), it upgrades to the most capable tier the item allows.
   - When time is short (less than 1 hour) or the grant is nearly used (less than 15% left), it downgrades one step.
   - It keeps downgrading while the item's estimated cost exceeds the remaining budget minus the floor. If no allowed tier fits, it skips the item.
6. It runs each item according to its mode:
   - `generate`: one router call, pinned to the grant's provider and the chosen model (opus → `claude-opus-5-5`, sonnet → `claude-sonnet-5-5`, haiku → `claude-haiku-5-5`). The org is set on the routing policy, so the grant guard can admit the call. Context comes from public `madfam-org` files fetched read-only. If none of an item's context files can be fetched, the item fails without calling the model.
   - `dispatch`: only the read-only `research` graph is allowed. The task goes through the durable outbox to `selva:task-stream`. Its model follows the org's task-type assignment, so the tier is advisory (`tier_enforced: false`).

The grant guard (lane LG) remains the hard stop. Calls past the ceiling or after expiry fail, and the item is marked `failed` with the error.

## Multi-step items

- **`fanout`.** An item can list several targets (services, repo files, task types). Each target is its own call and gets its own completed child task under the item's parent task (`parent_task_id`). Within an item, `parallel` targets run concurrently (default 2).
- **`refine_rounds`.** Each round runs three steps per target: a draft, a critique by an opus-tier critic against the item's acceptance criteria, and a revision. The child task keeps every step, along with its model, usage, latency and USD.
- **`output: json`** (the eval set). The reply is parsed and validated, with at least `json_min_items` items per target. If parsing fails, one repair call is made.
- **`mode: benchmark`** (`routing-benchmark`, `depends_on: eval-set-text-routing`). It takes the completed eval set, up to `per_task_type` prompts per task type. Each prompt is answered by `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` and the tenant's normal route (global org-config assignment, typically DeepInfra). One blind comparative opus-tier judge call then scores every answer against the rubric. The deliverable has two parts:
  - a per-task-type table: quality, p50 latency, USD and quality per USD;
  - a proposed `org_overrides.<org>.model_assignments` YAML, choosing the cheapest model within 0.05 of the best quality.
  - DeepInfra calls are recorded, but they are not charged to the grant tally.
- **Per-item budget.** An item stops starting new steps once its tally reaches `budget_share × ceiling`, then completes with what it has. Each step's USD is added to that tally (cost-model estimate; worst-case price if the cost model is unavailable). Each call is also metered to `compute_token_ledger` with the parent task id. With parallel targets, an item can overshoot its budget by at most `parallel` in-flight steps.
- **Resume.** A retried item skips targets that already have a completed child task, and starts its tally from those targets' recorded spend.

## Where outputs show up

- Each item is a swarm task in the platform org, labelled `credit-autopilot`, `line:<line>` and `<item id>`. You can find it two ways:
  - in the office UI task board, where completed items sit in the **Review** column;
  - through `GET /api/v1/swarms/tasks?…`.
- For generate items, the deliverable is stored in `payload.result.content` on the task. The same place records the provider and model used, token usage, the context files read and any context that was missing.
- `payload.credit_autopilot` records the item id, line, tier, model, the reason the tier was chosen and the grant id.
- **Live per-item status:** `payload.credit_autopilot.progress` on the parent task is rewritten after every target. It holds: `targets_total`, `targets_done`, `targets_failed`, `targets_skipped_budget`, `calls`, `spend_usd`, `budget_usd`, `budget_reached`. Each target's output sits on its child task. I chose this over a new endpoint because it needs no API model change, and the task view already renders payloads.
- **What each dollar bought:** `compute_token_ledger` rows carry `task_id`. Summing `cost_usd` by `task_id` gives the spend per item.
- Artifact files are not used: worker artifact storage is pod-local `/tmp`. The task row is the durable record.

## Operating notes (first production run, 2026-10)

What the first run taught, so the next grant goes further:

- **Empty completions.** On large code contexts, Opus 5.5's adaptive thinking can use the whole `max_output_tokens` budget, so no text block comes back and the target fails with `empty completion`. Those tokens are still billed. Review-style items now get 24k output tokens, but the largest review prompts still came back empty at 24k. Before the next run: record `stop_reason` and usage on empty completions, stream long generations, send `output_config.effort` explicitly, and keep each call's context smaller.
- **Refusals.** Acceptance criteria that asked for exploit scenarios drew model refusals (`AnthropicRefusalError`). Ask for a failure scenario and a patch instead.
- **Completed with failures.** An item that finishes with some targets done is `completed` and is never retried. To rerun only the failed targets, add a `*-topup` item that lists just those targets (the backlog test checks that a top-up only reruns a subset of its source item).
- **Restarts orphan work.** A workers rollout kills in-flight items. Their rows stay `running` and hold slots until the 60-minute staleness window passes. A rollout can also restart twice (the manifest env first, then the image digest commit). With a single workers replica, rows created before the current pod started cannot be live; an operator can mark them `failed` so the next tick re-dispatches them (the one-off script lives in the private operations repo). Avoid merging workers changes while items are in flight.
- **Meter versus provider billing.** The grant meter is Selva's own estimate. Compare it with the provider's console (or, later, its cost-report API) during the run and adjust `safety_margin_usd` in the grant; see `docs/PROVIDER_CREDIT_GRANTS.md` → Reconciling with the provider.

