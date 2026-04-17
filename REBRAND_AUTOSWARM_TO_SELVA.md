# Rebrand: AutoSwarm Office → Selva (selva.town)

**Date:** 2026-04-17
**Scope:** All of `autoswarm-office/` + 3 downstream env consumers
**Status:** Code-side complete. Infrastructure cutover remains (external action).

## Outcome

- **435 files touched, 2,189 text replacements** across the autoswarm-office repo.
- **14 Python module directories renamed** on disk + in git:
  - `autoswarm_workers` → `selva_workers`
  - `autoswarm_tools` → `selva_tools`
  - `autoswarm_permissions` → `selva_permissions`
  - `autoswarm_observability` → `selva_observability`
  - `autoswarm_skills` → `selva_skills`
  - `autoswarm_orchestrator` → `selva_orchestrator`
  - `autoswarm_memory` → `selva_memory`
  - `autoswarm_workflows` → `selva_workflows`
  - `autoswarm_plugins` → `selva_plugins`
  - `autoswarm_redis_pool` → `selva_redis_pool`
  - `autoswarm_sdk` → `selva_sdk`
  - `autoswarm_doctor` → `selva_doctor`
  - `autoswarm_a2a` → `selva_a2a`
  - `autoswarm_calendar` → `selva_calendar`
- **9 npm scopes renamed**: `@autoswarm/*` → `@selva/*`
- **87 tests still green** across budget-gate, doctor, enclii-cli, permissions/modes, factory-manifest, revenue-loop-probe.
- **3 downstream repos** (karafiel, proton-bridge-pipeline, autoswarm-sandbox) updated to reference `SELVA_*` env vars.

## Naming policy applied

| Where | Before | After |
|---|---|---|
| Display name | AutoSwarm Office, AutoSwarm | Selva |
| npm scope | `@autoswarm/*` | `@selva/*` |
| Python module (snake_case) | `autoswarm_workers` | `selva_workers` |
| Kebab identifiers / K8s | `autoswarm-workers` | `selva-workers` |
| Env vars | `AUTOSWARM_API_URL` | `SELVA_API_URL` |
| CamelCase classes | `AutoSwarmError` | `SelvaError` |
| Redis key prefix | `autoswarm:` | `selva:` |
| Primary domain | (unnamed) | `selva.town` |

## Intentionally preserved

| Pattern | Reason |
|---|---|
| `Áureo` (with diacritic) | Agent name — L7 Finance Controller in the roster. Unrelated to brand. |
| `nexus-api` / `nexus_api` / `NEXUS_API` | Implementation name for Selva's control plane. Kept distinct so docs can say "Selva's nexus-api" without confusion. |
| `selva.town` / `selvatown.com` | Target brand domain + existing redirect (untouched). |
| `autoswarm-sandbox` as a sibling-repo directory name | External repo; only its internal env var references were updated, not the repo dir itself. |
| `@sim4d/`, `@phyne/`, `@routecraft/`, `@dhanam/`, `@madfam/` scopes | Unrelated products. |

## External actions required (I couldn't do these from code)

These are outside the scope of a code sweep. Please schedule when convenient:

### 1. GitHub repository rename
- Rename `github.com/madfam-org/autoswarm-office` → `github.com/madfam-org/selva`
- GitHub auto-redirects the old URL for 30+ days, but update every consumer's git remote eventually:
  ```bash
  git remote set-url origin https://github.com/madfam-org/selva.git
  ```
- Update CI/CD that clones the repo by name.
- Update `.github/workflows/` references in other repos if any.

### 2. Local working directory rename
- `/Users/aldoruizluna/labspace/autoswarm-office/` → `/Users/aldoruizluna/labspace/selva/`
- Do this AFTER the current session ends (renaming the CWD mid-session breaks tooling).
- Any shell aliases, tmux pane scripts, or IDE workspace configs referencing the old path need updating.

### 3. DNS / domain rollout (`selva.town`)
- Per `internal-devops/ecosystem/domain-map.md`, `selvatown.com` already 301-redirects to `selva.town` (active).
- Provision the primary subdomains on `selva.town` that were previously on `*.madfam.io`:
  - `agents.madfam.io` → `app.selva.town` (office UI)
  - `agents-api.madfam.io` → `api.selva.town` (nexus-api)
  - `agents-admin.madfam.io` → `admin.selva.town` (admin)
  - `agents-ws.madfam.io` → `ws.selva.town` (colyseus)
- Keep the `*.madfam.io` URLs as CNAMEs (or 301 redirects) for a grace period.
- Update `enclii.yaml` domain declarations (in-code change done as part of this commit — but DNS + Cloudflare Tunnel config are external).

### 4. Kubernetes namespace
- Current namespace: `autoswarm` (preserved in K8s manifests for now — changing it live breaks running pods).
- Migration path: create new `selva` namespace, deploy alongside, cutover traffic, decommission old.
- This is a live-ops task — see `docs/runbooks/` for the generic namespace-migration playbook.

### 5. Vault / secret paths
- Any Vault paths under `autoswarm/*` should be copied to `selva/*` then old paths revoked.
- ExternalSecrets referencing `autoswarm/*` paths remain valid until secrets are rotated.

### 6. Slack / PostHog / Sentry project names
- Slack channels `#autoswarm-*` → `#selva-*` (carry history via rename, don't delete).
- PostHog project name: rename the project (events and user identities stay).
- Sentry project names: `autoswarm-workers` / `autoswarm-nexus-api` etc. → `selva-workers` / `selva-nexus-api`. Old DSNs remain valid; rename is cosmetic.

### 7. Docker image tags
- Old images under `ghcr.io/madfam-org/autoswarm-office/*` keep working.
- Next builds should push to `ghcr.io/madfam-org/selva/*` — the CI pipeline config drives this; update the image name in each service's build workflow.

## Verification

The in-code rebrand is complete when this returns zero matches (excluding intentional preserves):

```bash
cd /Users/aldoruizluna/labspace/autoswarm-office
grep -rhEi "autoswarm" \
  --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.venv \
  --exclude-dir=__pycache__ --exclude-dir=.mypy_cache \
  --exclude-dir=dist-info --exclude-dir=egg-info \
  . 2>/dev/null | grep -vE "autoswarm-sandbox" | head
```

## Related

- Rebrand script: `/tmp/autoswarm_to_selva.py` (not committed; pattern list inlined above for audit).
- Prior rebrands same shape:
  - `memory/project_sim4d_rebrand.md` (BrepFlow → Sim4D)
  - `memory/project_aureo_to_madfam_rebrand.md` (Aureo Labs → Innovaciones MADFAM)
