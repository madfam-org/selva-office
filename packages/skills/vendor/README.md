# Vendored skills

## impeccable (UI/UX)

MADFAM standing rule: [impeccable](https://github.com/pbakaus/impeccable)
(Apache-2.0, by Paul Bakaus) is used for any and all UI/UX work, by Selva's
agents and by people and coding agents working on Selva's own UI.

| Path | What | Edit by hand? |
|---|---|---|
| `impeccable/` | Verbatim upstream files at the pinned tag: `SKILL.md`, `reference/**` (the 24 command playbooks), `scripts/VERSION`, `scripts/command-metadata.json`, `LICENSE`, `NOTICE.md` | Never |
| `impeccable.pin.json` | The pin: tag, commit, npm + engine versions, npm `sha512` of each engine binary package, sha256 of every vendored file | Never |
| `impeccable.adapter.md` | Selva harness adapter: how the upstream skill maps onto Selva workers (no launcher, no roll API, telemetry off, completion contract, precedence) | Yes, then `render` |
| `../skill-definitions/impeccable/SKILL.md` | Generated: adapter + verbatim upstream `SKILL.md` body + verbatim `craft-floor.md` | Never |

Left out on purpose: the upstream launcher, live-mode browser bundles, the font
index and the Codex sub-agent TOMLs. Selva workers do not run them.

### How Selva uses it

- `selva_skills.impeccable.is_ui_ux_task` marks a task UI/UX (payload
  `ui_ux: true`, a named `impeccable_command`, or UI vocabulary in a coding
  task); the worker then adds the `impeccable` skill and the verbatim
  reference of the named command to the agent's prompt.
- The `impeccable_detect` tool runs the pinned engine (`impeccable detect
  --json`) on changed UI files: read-only, telemetry off, minimal environment.
- The coding graph's `ui_audit` node runs it after the tests pass. Changed UI
  files make any coding task UI/UX. Primary findings get one more implement
  round; the review must justify any that remain; the summary goes to the
  push-gate approval and to the task result. `SELVA_IMPECCABLE_ENFORCEMENT`:
  `warn` (default) or `block`.

### Updating the pinned version

```bash
# 1. Check out the upstream release tag (skill and CLI ship from the same commit).
git clone --depth 1 --branch skill-v<X.Y.Z> https://github.com/pbakaus/impeccable /tmp/impeccable

# 2. Re-vendor, re-pin (reads engine integrity from registry.npmjs.org), re-render SKILL.md.
python3 scripts/vendor-impeccable.py sync --source /tmp/impeccable --npm-version <X.Y.Z>

# 3. Verify and review.
python3 scripts/vendor-impeccable.py check
uv run pytest packages/skills/tests/test_impeccable_skill.py \
  packages/tools/tests/test_impeccable_detect.py apps/workers/tests/test_ui_audit.py -q
git diff --stat packages/skills/
```

`sync` refuses a checkout that is not at `skill-v<X.Y.Z>`, and an npm release
whose engine differs from the skill's `scripts/VERSION`. Read the upstream
changelog and the diff of `impeccable/SKILL.md` and `reference/` before opening
the PR; adjust `impeccable.adapter.md` if the upstream setup flow changed. The
workers image picks up the new engine on its next build (`Dockerfile.workers`
runs `fetch-engine`, which verifies the pinned `sha512`).

Local detector runs: `python3 scripts/vendor-impeccable.py fetch-engine --dest
<dir>` and `export IMPECCABLE_BIN=<dir>/impeccable` (or
`SELVA_IMPECCABLE_ALLOW_NPX=1` to use `npx --yes impeccable@<pinned>`).
Always with `IMPECCABLE_NO_TELEMETRY=1 DO_NOT_TRACK=1`.
