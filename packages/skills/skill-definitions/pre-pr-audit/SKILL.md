---
name: pre-pr-audit
description: Before opening a PR, audit the working diff for test + doc + config gaps — surface changes that shipped without matching tests, docs, or env updates — and remediate or flag them. Gate PR submission on critical gaps.
audience: tenant
allowed_tools:
  - file_read
  - file_write
  - bash_execute
  - lint_and_typecheck
  - test_coverage_for_diff
  - git_create_pr
  - deploy_preflight
metadata:
  category: quality
  complexity: medium
---

# Pre-PR Audit Skill

You run **immediately before opening a PR**, after the implementation is complete and locally verified. Your job is to catch the gap between *what changed* and *what was tested + documented*, then close the closable gaps and flag the rest.

This is different from `code-review`, which is a post-hoc quality check. `pre-pr-audit` is a **pre-submission gate**: it blocks PR creation if the diff ships code that isn't tested, exposes config no one documented, or introduces public API no docs mention.

## When to invoke

- User says "audit tests and docs", "close gaps", "ready to PR", or similar.
- Coding skill has just finished an implementation loop and the agent is about to open a PR.
- CI is green but the agent has not yet confirmed doc coverage.

## Inputs

- Working tree state (uncommitted + committed-but-unpushed).
- Base branch (default `main`) — diff compared against this.
- Repo conventions (CLAUDE.md, .env.example, README.md, docs/).

## Audit passes

Run these **in order**. Each emits findings; findings accumulate into the final report.

### 1. Surface-delta pass

From `git diff <base>...HEAD` + uncommitted changes:

- **Added public surface** — new exported functions/classes/types, new HTTP endpoints, new CLI flags, new env vars, new DB columns.
  - For each, check: does a test exercise it? (grep for the symbol in `tests/`, `*.test.*`, `test_*.py`.)
  - For endpoints: is the path referenced in an API doc / OpenAPI schema / README?
  - For env vars: is it in `.env.example`? Is it in `CLAUDE.md` if it's load-bearing?
- **Changed public surface** — signature changes, response-shape changes, renamed symbols.
  - Are existing tests updated to the new shape?
  - Is the change mentioned in CHANGELOG / MIGRATION if the repo has one?
- **Removed public surface** — deletions.
  - Grep the rest of the repo for references to the removed symbol. None should remain.
  - If the deletion is intentional, look for a deprecation note that's now obsolete.

### 2. Doc-coherence pass

- `CLAUDE.md` — stale status tables, missing mention of new subsystem, outdated architecture diagrams.
- `README.md` — Quick Start missing new commands, missing install steps for new deps.
- `.env.example` — every new env var documented with a comment explaining purpose + fallback behavior.
- `docs/` — any file whose subject overlaps the changed code should be checked for staleness.

### 3. Test-coverage-for-diff pass

Use the `test_coverage_for_diff` tool — it runs coverage scoped to the
diff vs the base ref and returns structured `{file, uncovered_lines}`
findings without you having to parse pytest output.

```
test_coverage_for_diff(base_ref="main", repo_path=".")
→ {uncovered: [...], summary: {files_changed, changed_lines_uncovered}}
```

Any entry in `uncovered` is a 🔴 finding. If `changed_lines_uncovered
== 0` but no test files changed, downgrade to 🟡 (tests may have existed
already and just exercised the new code).

### 4. Style + types pass

Use the `lint_and_typecheck` tool — it runs ruff + mypy (Python)
and/or eslint + tsc (TypeScript), auto-detects language, and returns
structured findings. Missing toolchains are skipped (not errored) so
a Python-only repo without pnpm won't trip this pass.

```
lint_and_typecheck(paths=["."], repo_path=".")
→ {findings: [{tool, severity, file, line, code, message}], skipped: [...]}
```

Every `severity: error` finding is a 🔴 blocker. Warnings are 🟡.

### 5. Config-and-secrets pass

- New secrets referenced in code? Check they're templated in `.env.example` (with placeholder value).
- New k8s manifests? Run `deploy_preflight(overlay_path="infra/k8s/<overlay>")` — it surfaces un-pinned images, missing resource requests, missing `privileged: false`, and other Kyverno-policy blockers. `verdict: "blocked"` → 🔴.
- New external service dependency? CLAUDE.md should call it out so operators know.

## Severity

- **🔴 blocker** — PR must not be opened until closed. Examples: new endpoint untested, new env var undocumented, removed symbol still referenced elsewhere.
- **🟡 worth-doing** — should fix in this PR but can be a follow-up if scope-creep is real. Examples: stale status table, missing Quick Start example.
- **🟢 nice-to-have** — flag in the PR description, don't block. Examples: minor README polish, doc cross-references.

## Remediation

For 🔴 and 🟡 findings, **close them in the same PR** whenever the fix is local:

- Missing `.env.example` entry → add with a comment explaining purpose + fallback.
- Missing test → write it (use the `coding` skill's test patterns).
- Stale CLAUDE.md status → update the specific field, don't rewrite.
- Missing doc section → add one paragraph + a code example; don't pad.

For findings you can't close (e.g. an external doc that requires another team's sign-off), add a bullet to the PR description under `## Follow-ups` so the reviewer has the full picture.

## Output contract

Return structured JSON:

```json
{
  "verdict": "ready" | "needs-remediation" | "blocked",
  "surface_delta": {
    "added": [{"kind": "endpoint", "symbol": "POST /v1/render/card", "tested": true, "documented": true}],
    "changed": [...],
    "removed": [...]
  },
  "findings": [
    {"severity": "blocker|worth-doing|nice-to-have",
     "category": "test|doc|config|surface",
     "file": "path/to/file",
     "description": "...",
     "remediation": "action taken | follow-up noted | requires external review"}
  ],
  "remediations_applied": <int>,
  "follow_ups_logged": <int>,
  "test_coverage_delta": {"files_changed": N, "files_with_new_tests": M}
}
```

## Gating rules

- `verdict = "blocked"` → do NOT call `git_create_pr`. Return the finding list to the caller.
- `verdict = "needs-remediation"` → close the closable gaps, re-run the audit, then proceed.
- `verdict = "ready"` → call `git_create_pr(title=..., body=...)` to create the PR. The tool enforces additional guards (protected branch refuse, conventional-commit warning, CODEOWNERS auto-reviewers, PR template fallback) — include the audit report in the body under `## Pre-PR Audit`.

## Non-goals

- You do NOT enforce style/lint — that's the `coding` skill + CI.
- You do NOT review correctness — that's the `code-review` skill.
- You do NOT run the full test suite — just the slice that touches the diff.
- You do NOT decide whether a change is *good*; you decide whether it's *complete*.

## Example invocation

```
Caller: "Audit tests and docs before I open the PR for the CEQ render pipeline."

Skill:
1. git diff main...HEAD
2. Grep new symbols, check test coverage
3. Check CLAUDE.md, README.md, .env.example for staleness
4. Emit findings, close 🔴/🟡, log 🟢 as follow-ups
5. Return verdict + report → caller proceeds or blocks
```
