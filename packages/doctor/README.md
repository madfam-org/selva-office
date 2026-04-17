# autoswarm-doctor

Preflight check for the Selva / AutoSwarm runtime.

Answers one question: **is this environment ready to start autonomous work?**

Inspired by the `/doctor` surface in `ultraworkers/claw-code`; the
implementation is ours. Part of closing GAP-15 in
`docs/SELVA_SWE_PARITY.md`.

## Install + run

```bash
pip install -e packages/doctor
autoswarm-doctor              # plain-text output, exit 0/1
autoswarm-doctor --json       # JSON, still honours exit code
```

Exit codes: `0` if no FAIL checks, `1` otherwise. WARN checks do not
block exit.

## What it checks (v0.1)

| Name | Purpose | Status meaning |
|---|---|---|
| `env.required` | `DATABASE_URL`, `REDIS_URL`, ops env vars | FAIL if required unset; WARN if recommended unset |
| `database.url` | Plausible Postgres URL, no placeholder creds | WARN on `insecure`/`change-me` substrings |
| `redis.url` | `redis://` or `rediss://` | WARN on unusual scheme |
| `binary.git` | Git on PATH | FAIL if missing (required) |
| `binary.enclii` | Enclii CLI on PATH | FAIL if missing (required — closes GAP-2) |
| `binary.gh` | GitHub CLI on PATH | WARN if missing (optional) |
| `binary.kubectl` | kubectl on PATH | WARN if missing (fallback only) |
| `selva.reachable` | `GET {SELVA_API_BASE}/models` | FAIL on 401/5xx/connection error |
| `bridge.deepinfra` | `DEEPINFRA_API_KEY` when bridge active | SKIP if unset; PASS if present (masked) |
| `git.identity` | `user.name` / `user.email` set | WARN if unset (GitTool fallback kicks in) |

Total runtime target: **under 5 seconds** from cold cache; checks run in
parallel.

## Extending

```python
from autoswarm_doctor import Check, CheckStatus, Doctor

async def check_custom_thing():
    return Check("custom.thing", CheckStatus.PASS, "all good")

report = await Doctor(checks=[check_custom_thing]).run()
```

Contract:
* Never raise. Return a `Check` with `status=FAIL`.
* Complete in under ~3 s. Longer checks go behind a future `--slow` flag.
* Be honest about SKIP vs PASS vs WARN. SKIP means "I can't tell", not
  "good".

## Related

* `docs/SELVA_SWE_PARITY.md` — the capability map this package closes.
* `CLAUDE.md` — production env var contract.
* `docs/runbooks/BRIDGE_DEEPINFRA.md` — what `bridge.deepinfra` is verifying.
