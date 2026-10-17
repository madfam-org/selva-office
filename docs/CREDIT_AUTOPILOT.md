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

## Turning it on (platform admin)

1. **Roster.** Run this once against the target environment with a platform-admin token. Re-running it is safe.

   ```bash
   SELVA_API_URL=<nexus-api base URL> SELVA_TOKEN=<platform-admin token> \
     python scripts/seed-madfam-factory-lines.py --org-id <platform org id>
   ```

2. **Grant.** In the Vault grant JSON (contract C1), set the grant to `"autopilot": true`.
3. **Workers.** Set the env `CREDIT_AUTOPILOT_ENABLED=true` on the workers Deployment. The autopilot is off without it.
4. **Optional tuning.** These env vars adjust the loop:
   - `CREDIT_AUTOPILOT_INTERVAL_SECONDS` (default 180)
   - `CREDIT_AUTOPILOT_MAX_CONCURRENCY` (default 2)
   - `CREDIT_AUTOPILOT_FLOOR_USD` (default 2)
   - `CREDIT_AUTOPILOT_MAX_ATTEMPTS` (default 2)
   - `CREDIT_AUTOPILOT_BACKLOG_PATH`

   `CREDIT_AUTOPILOT_ORG_ID` may restate the platform org, but if it names any other org the loop refuses to run.

The autopilot needs lane LG's `madfam_inference.grants.get_grant_statuses()`. If that function is missing, the loop logs that it is idle and does nothing.

## How it chooses

On each tick, the loop works through these steps in order:

1. It picks the soonest-expiring live grant that has `autopilot: true`, for the `anthropic` provider.
2. It starts no new work if any of these hold:
   - the pace is `ahead`, `exhausted` or `expired`;
   - the remaining budget is at or below the floor;
   - expiry is less than 15 minutes away.
3. It frees slots up to `max_concurrency`. A row that is still in flight with no update for 45 minutes counts as a failed attempt.
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

## Where outputs show up

- Each item is a swarm task in the platform org, labelled `credit-autopilot`, `line:<line>` and `<item id>`. You can find it two ways:
  - in the office UI task board, where completed items sit in the **Review** column;
  - through `GET /api/v1/swarms/tasks?…`.
- For generate items, the deliverable is stored in `payload.result.content` on the task. The same place records the provider and model used, token usage, the context files read and any context that was missing.
- `payload.credit_autopilot` records the item id, line, tier, model, the reason the tier was chosen and the grant id.
- **What each dollar bought:** `compute_token_ledger` rows carry `task_id`. Summing `cost_usd` by `task_id` gives the spend per item.
- Artifact files are not used: worker artifact storage is pod-local `/tmp`. The task row is the durable record.
