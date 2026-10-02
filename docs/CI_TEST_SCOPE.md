# CI Test Scope

Date: 2026-06-04
Owner: Selva engineering

This document defines which test suites are enforced on every PR and which are
intentional non-PR gates. It closes GA-008 from the commercial GA remediation
contract.

## Enforced on every PR

| Workflow job | Scope | Owner |
|---|---|---|
| `lint-ts` | Turbo TypeScript lint across workspace packages with `lint` scripts | Frontend/platform |
| `typecheck` | Turbo TypeScript typecheck; upstream package builds run first | Frontend/platform |
| `test-ts` | Turbo TypeScript tests across workspace packages with `test` scripts | Frontend/platform |
| `lint-py` | Ruff across the Python workspace | Backend/platform |
| `typecheck-py` | Workspace advisory mypy plus zero-regression ratchets for nexus-api, workers, and packages | Backend/platform |
| `test-py` root unit tests | `tests/unit` with coverage artifact | Backend/platform |
| `test-py` Wave 0 regressions | Inference router, budget gate, pgvector memory, campaign graph, approval agent-name response | Backend/platform |
| `critical-path-coverage` | Auth, RLS, onboarding, dispatch, outbound governance, artifact storage, worker auth/lifecycle | Backend/platform |
| `critical-path-coverage` inference sensitivity | `X-Sensitivity` fail-closed, sensitivity-before-task_type routing, per-tenant floors/caps/rate limits, no prompt or completion persisted | Backend/platform |
| `build` | Turbo production build after TS/Python tests | Release engineering |
| `security` | Trivy filesystem scan for HIGH/CRITICAL issues | Security |

## Non-PR Gates

| Suite | Trigger | Owner | Reason |
|---|---|---|---|
| `tests/e2e` / Playwright | Release candidate, staging promotion, or UI-risk PR | Frontend/platform | Browser suites are slower and need stable app services |
| `tests/load` / k6 | Manual `load-test.yml` and Phase 0 Run 4b evidence | Operations | Load tests are capacity exercises, not per-PR correctness checks |
| Production smoke scripts | Staging/prod promotion workflows | Operations | They are environment-targeted and side-effectful |
| Full Python workspace `uv run pytest apps packages tests` | Scheduled hardening run or high-risk refactor | Backend/platform | Some package suites require external services, pgvector, or long-running fixtures |
| Community skill lint deep checks | Pull requests touching `packages/skills/community-skills/` | Skills owner | Advisory by design until community skill fixtures are normalized |

## Conditional skips and known gaps (inventory 2026-10-01)

There are no `.only`, `it.skip`, `describe.skip`, unconditional
`pytest.mark.skip` or `xfail` markers in the repo. These conditional skips
remain, and each depends on the environment:

| Test | Skips when | CI status |
|---|---|---|
| `apps/nexus-api/tests/test_rls_strict_mode.py` (`postgres_only`) | the test database is not PostgreSQL (conftest pins SQLite) | **Not run by any CI step.** The strict-RLS assertions only run when someone points `DATABASE_URL` at PostgreSQL locally. Gap: add the file to `test-py`, which already has a pgvector PostgreSQL service. |
| `apps/nexus-api/tests/test_tracing_middleware.py` (one case) | `opentelemetry` is not importable | Not in a CI step. Runs in the full-workspace hardening run. |
| `packages/budget-gate/tests/test_api.py` | `fastapi`/`httpx` missing (`importorskip`) | Both are installed by `uv sync`, so it runs wherever it is invoked. |
| `packages/tools/tests/test_k8s_secret.py` (one case) | the nexus-api audit module is not importable | Runs in the full-workspace hardening run. |

**Known red outside PR CI:** `packages/skills/tests/test_community_skills.py`
has 5 failures on `main` (2026-10-01). It expects 25 community skills and
finds 27. `community-skills/video-downloader/SKILL.md` declares the name
`youtube-downloader`, which does not match its directory. The file is not in
any PR job. It belongs to the community-skills owner (see the Non-PR Gates
table).

The JWT verification tests (`test_auth_coverage.py`,
`test_auth_pyjwt_verification.py`, `test_auth_worker_token_scoping.py`) run in
`critical-path-coverage`. `test_auth_pyjwt_verification.py` signs real RS256
tokens against a test JWKS and checks the contract in `SECURITY.md` ("Janua
JWT verification (nexus-api)"); `test_auth_coverage.py` mocks PyJWT to cover
the routing branches.

## Change Rule

Any new tenant-safety, money-path, outbound-action, or dispatch-contract
regression test must be included in either the always-on CI scope above or this
document's non-PR gate table with an owner and trigger.

## Session Evidence

- [SESSION_2026-06-05_COMMERCIAL_GA_CI_RESTORATION.md](./SESSION_2026-06-05_COMMERCIAL_GA_CI_RESTORATION.md)
  records the 2026-06-04 `CI` / `Schema Drift` restoration pass, including the
  Ruff, generated wire type, Trivy lockfile, workflow safe-eval, and local
  pgvector verification notes.
