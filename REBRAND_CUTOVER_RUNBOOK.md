# AutoSwarm → Selva Production Cutover Runbook

**Branch:** `chore/2026-04-17-madfam-ecosystem-sweep`
**Target merge date:** TBD — pick a known maintenance window
**Expected cutover duration:** 45–90 minutes
**Blast radius:** `selva.town` + `agents-api.madfam.io` (currently
served by autoswarm-office's `nexus-api` in the `autoswarm` namespace).
**Rollback window:** every step below is reversible up to Step 7.

---

## 0. Why this is a coordinated cutover, not a merge

Pushing the feature branch to `main` triggers the
`.github/workflows/deploy.yml` auto-build → Enclii deploy → K8s apply
chain. The branch contains:

  - 3,982 files changed; ~1M insertions / ~4k deletions
  - Package imports: `autoswarm_tools` → `selva_tools`,
    `autoswarm_a2a` → `selva_a2a`, `autoswarm_observability` → …,
    `autoswarm_redis_pool` → … (5 Python packages renamed at the
    package level — Python import errors on mismatch, not runtime
    degraded behaviour)
  - Config env vars: every `AUTOSWARM_*` → `SELVA_*`, including
    `AUTOSWARM_SKILLS_DIR` → `SELVA_SKILLS_DIR`,
    `AUTOSWARM_STATE_DB_PATH` → `SELVA_STATE_DB_PATH`,
    `AUTOSWARM_WEBHOOK_SECRET` → `SELVA_WEBHOOK_SECRET`,
    `AUTOSWARM_VAULT_NAMESPACE` → `SELVA_VAULT_NAMESPACE` (5 vars).
  - K8s namespace intent: `autoswarm` → `selva` (if we cut this over).
  - Vault path intent: `secret/autoswarm/*` → `secret/selva/*`.

Doing these piecemeal = production outage. Doing them in one
coordinated window = ~30s of downtime during the pod roll.

---

## 1. Prerequisites (do these days before, not during the window)

- [ ] Fresh DB backup of `autoswarm` namespace Postgres (point-in-time
      restore ready). Tag as `pre-selva-cutover`.
- [ ] Fresh Redis RDB snapshot of the `autoswarm`-namespace Redis.
- [ ] Vault: verify `secret/autoswarm/*` paths exist and are readable
      (they become the source for the new `secret/selva/*` paths in
      Step 3).
- [ ] Cloudflare tunnel entries ready for `*.selva.town` (DNS + tunnel
      route config in `infra/cloudflare/redirect-rules.yaml` —
      already committed to the branch).
- [ ] On-call acknowledged. Status page updated to "maintenance
      window: MADFAM platform cutover, ~60 min."
- [ ] Revert-branch ready: create `revert/pre-selva-cutover` at the
      current `main` tip so Step 8 rollback is one force-push away if
      everything catastrophically goes wrong.

---

## 2. Cutover window — minute-by-minute

**T+0** — Announce maintenance start in Slack / status page.
**T+1** — Scale the autoswarm-namespace deployment replicas to 0:

```sh
kubectl -n autoswarm scale deployment --all --replicas=0
```

Confirm with `kubectl -n autoswarm get pods` — no running pods.

---

## 3. Vault path migration

Copy every autoswarm path into its selva counterpart. The values don't
change; only the path does.

```sh
# Dry-run first — enumerate what we'll copy:
vault kv list secret/autoswarm

# Copy each path (this loop is idempotent — re-running overwrites the
# target with the same value):
for k in $(vault kv list -format=json secret/autoswarm | jq -r '.[]'); do
  vault kv get -format=json "secret/autoswarm/$k" \
    | jq '.data.data' \
    | vault kv put "secret/selva/$k" -
done

# Verify counts match:
vault kv list secret/autoswarm | wc -l
vault kv list secret/selva     | wc -l    # expect equal
```

Do NOT delete `secret/autoswarm/*` yet — keep them as an in-place
rollback target until Step 7 confirms success.

---

## 4. K8s namespace cutover

The branch ships with K8s manifests referencing the `selva` namespace.
Create it, apply the manifests, and let ESO re-materialise the secrets
from the new Vault paths.

```sh
# Create the namespace if it doesn't exist (idempotent):
kubectl create namespace selva --dry-run=client -o yaml | kubectl apply -f -

# Apply the rebranded manifests from the feature branch:
git fetch origin chore/2026-04-17-madfam-ecosystem-sweep
git checkout origin/chore/2026-04-17-madfam-ecosystem-sweep -- infra/k8s/
kubectl apply -k infra/k8s/production/

# ESO should reconcile within ~15 min (refresh interval). Force it:
kubectl -n selva annotate externalsecret --all \
  force-sync=$(date +%s) --overwrite
```

Verify the new secrets exist:

```sh
kubectl -n selva get secrets
# expect: selva-secrets, selva-admin-auth, (others per manifest)
```

---

## 5. Merge the branch to main

At this point the infra is ready to accept the rebuild that `main`
will trigger.

```sh
cd /Users/aldoruizluna/labspace/autoswarm-office
git fetch origin main
git checkout main && git pull
git merge chore/2026-04-17-madfam-ecosystem-sweep --no-ff \
  -m "chore: AutoSwarm -> Selva rebrand + ecosystem sweep cutover

Complete namespace + package + env-var rename. Merged as part of a
planned cutover window per REBRAND_CUTOVER_RUNBOOK.md."
git push origin main
```

`.github/workflows/deploy.yml` fires. Watch the Actions tab:

```sh
gh run watch --exit-status
```

Expect: build succeeds (Python packages now resolve as `selva_*`),
image pushed to `ghcr.io/madfam-org/selva-nexus-api:latest`, Enclii
deploy notified.

---

## 6. Enclii redeploys into the `selva` namespace

Enclii reads `.enclii.yml` which (on this branch) declares the `selva`
namespace target. Confirm:

```sh
enclii status --service nexus-api
# expect: namespace=selva, replicas running > 0
```

Health probe:

```sh
curl -fsS https://agents-api.madfam.io/api/v1/health
# expect: {"status":"healthy","service":"nexus-api"}

curl -fsS https://selva.town/status
# expect: HTML renders, probe status block visible (may be "No run yet"
# if the revenue-loop-probe CronJob hasn't run since the namespace
# changed — that's fine, next cycle will populate it)
```

---

## 7. Verification gate (30 min soak)

Before retiring the autoswarm namespace:

- [ ] `kubectl -n selva get pods` — all Ready.
- [ ] No 5xx in Grafana on the past 30 min.
- [ ] One real probe run has completed (`/status` shows a correlation
      id from the new namespace).
- [ ] Janua JWT verification works (try an authenticated call to
      `/api/v1/swarms/dispatch` and confirm 200).
- [ ] Worker can pick up a test task from the new Redis Streams.
- [ ] Enclii's webhook into `selva-nexus-api` works (dispatch a test
      deploy event and see it land in the gateway).

If ANY of these fail: go to Step 8 before the 30-min gate ends.

---

## 8. Rollback (if Step 7 fails)

Up to this point, `secret/autoswarm/*` and the autoswarm-namespace
deployments are still in place (just scaled to 0). Rollback is:

```sh
# Scale autoswarm back up:
kubectl -n autoswarm scale deployment --all --replicas=1

# Scale selva down:
kubectl -n selva scale deployment --all --replicas=0

# Revert main:
git checkout main
git reset --hard origin/main^  # back out the merge
git push --force-with-lease origin main  # !!! only with explicit human approval

# Enclii auto-deploy fires, builds the old (pre-rebrand) image.
```

This returns traffic to the autoswarm namespace within ~5 min.
Post-mortem what broke before re-attempting.

---

## 9. Retire the autoswarm namespace (only after 24h stable on selva)

- [ ] Snapshot `secret/autoswarm/*` to cold storage.
- [ ] `vault kv metadata delete secret/autoswarm/...` (per path).
- [ ] `kubectl delete namespace autoswarm` — irrecoverable; be sure.
- [ ] Cloudflare: retire old `*.autoswarm.internal` tunnel routes.

---

## Appendix A — Dependency matrix

| Component | Reads | Writes | Blocks others |
|---|---|---|---|
| Nexus-API | `selva-secrets`, Postgres, Redis | Postgres, Redis, Events API | Colyseus + Workers + Office-UI |
| Workers | `selva-secrets`, Redis streams | Postgres (tasks), Events API | None downstream |
| Colyseus | `selva-secrets`, Redis | Redis | Office-UI |
| Office-UI | Public `/v1/billing/catalog` + `/v1/chat` | None | None |
| Revenue-loop probe | `selva-secrets` (probe tokens) | Nexus `/probe/runs` | None (CronJob) |

The Colyseus state is the fragile joint — active player sessions drop
when it rolls. Warn users in-office of the maintenance window.

## Appendix B — Commits on the cutover branch

```
5367faa  test(selva): close pricing-intel + bundles test gaps; refresh docs
d77ebca  feat(selva): secret-access audit-trail emitter + wire into all vault tools
0f72659  feat(selva): selva.town/bundles — live à-la-carte bundle calculator
d98bf64  feat(selva): weekly pricing-intel CronJob + CLI runner
167cd9d  chore(selva): remove RouteCraft from catalog UNPRICED_PRODUCTS list
1bdf308  feat(selva): pricing-intelligence skill + 4 catalog-audit tools
e274e92  feat(selva): unified offer-catalog view at selva.town/catalog
8638495  feat(selva): HITL confidence Sprint 1 — observe-only decision ledger
941c7a2  feat(selva): revenue-loop probe endpoints + public /status page (A.7)
65db985  refactor: AutoSwarm Office → Selva (selva.town) complete rebrand
b6e8fd6  feat(ecosystem): Selva SWE parity + shared packages + DeepInfra bridge
```

If you want to split the rebrand OUT of the merge (Option 1b in your
triage), cherry-pick all commits EXCEPT `65db985` onto a fresh branch,
merge that first, and schedule the rebrand for a later window.
