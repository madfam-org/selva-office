# selva-autoheal

Infra self-healing agents for the MADFAM platform, v1: alert intake, read-only
diagnosis under a per-incident budget, and remedy proposals for a human to
apply. Design, decisions and owner steps: [RFC 0047](../../docs/rfcs/0047-infra-self-healing-agents.md).

**Hard rule: v1 never writes to production.** The toolbox can only read and
dry-run Enclii; the apply half of Enclii's plan-hash contract cannot be
expressed.

| Module | Role |
|---|---|
| `alerts` | Alertmanager webhook v4 model, incident key (`groupKey`), qualification |
| `store` | Redis: dedup/cooldown, flap and daily limits, kill switch, queue, daily spend |
| `budget` | Per-incident and per-day caps, worst case admitted before each call |
| `tools` | Read-only Enclii toolbox and its allowlist |
| `signatures` | Fixed probes and deterministic known-incident signatures |
| `agent` | Evidence first, then a bounded JSON-protocol model loop |
| `report` / `courier` | Telegram text with the plan hash; angelia Courier envelope |
| `testing` | Test doubles (recorded Enclii, scripted model, fake Courier) |

Tests: `uv run pytest packages/autoheal/tests` (includes the recorded
2026-10-24 CNPG incident replay).
