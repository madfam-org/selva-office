# Selva SWE Parity — vs. `ultraworkers/claw-code`

**Purpose.** Single source of truth for what Selva's SWE surface must
cover to stand on its own as the MADFAM ecosystem's autonomous software
engineer. We don't copy claw-code — we use it as a capability checklist.

**Why not absorb the code.**
- `ultraworkers/claw-code` ships with **no license** at the repo level.
  Without an explicit grant, lifting source is a copyright risk.
- The repo explicitly disclaims "This repository is **not affiliated with,
  endorsed by, or maintained by Anthropic**" while admitting it's a Rust
  reimplementation of Anthropic's proprietary Claude Code. That's doubly
  dicey for MADFAM — we don't want to inherit that exposure.
- Our agent stack is LangGraph-on-Python, not Rust. A literal port would
  be a waste even if the license were clean.

**What we do absorb.** The *capability surface* — tool names, permission
modes, session conventions, config hierarchy, CLI affordances — i.e.
the bits that are functional design, not expression. Same approach every
agent framework takes (bash / read / write / grep are not proprietary).

**Contract this document encodes.**
1. An autonomous Selva agent must never stall asking "may I use this
   tool?". Policy lives in the permission matrix; execution flows.
2. HITL approval only triggers when the matrix says `ASK` for the
   specific action category in the active permission mode.
3. Operational binaries (`enclii`, `kubectl` where allowed, `gh`, `git`)
   must be present and authenticated in the worker image. A missing binary
   is a `/doctor` failure, not a runtime surprise.

---

## Capability matrix

Legend: ✅ parity, ⚠️ partial / gap identified, ❌ missing, 🟢 we exceed.

### Tool surface

| Capability | claw-code | Selva today | Target / action |
|---|---|---|---|
| `bash` (command execution) | ✅ | ✅ `BashTool` in `packages/tools` | 🟢 plus SSRF protection + sandbox flags already there |
| `read` (file) | ✅ | ✅ `ReadTool` | 🟢 + path-traversal guard |
| `write` (file) | ✅ | ✅ `WriteTool` | ✅ |
| `edit` (patch) | ✅ | ✅ `EditTool` + `MultiEdit` | 🟢 MultiEdit not in claw parity table |
| `grep` | ✅ (chunk assembly) | ✅ `GrepTool` | ✅ |
| `glob` | ✅ | ✅ `GlobTool` | ✅ |
| web search / fetch | ✅ | ✅ `web.py` tools + SSRF-safe HTTP | ✅ |
| sub-agent / agent spawn | ✅ | ✅ A2A package + Puppeteer orchestrator | 🟢 Thompson bandit selection |
| todo tracking | ✅ | ✅ TodoWrite (shared SDK pattern) | ✅ |
| notebook editing | ✅ | ✅ `NotebookEdit` | ✅ |
| MCP server lifecycle + inspection | ✅ | ✅ `McpToolAdapter` + stdio/HTTP transports | ✅ |
| session persistence + resume | ✅ (`--resume latest`) | ⚠️ `checkpoints.py` persists but no CLI affordance | **GAP-1:** add resume-latest entry point |
| cost / usage / stats | ✅ | 🟢 `compute_token_ledger` + `/metrics/dashboard` | 🟢 DB-backed, not just session |
| git integration | ✅ | ✅ `GitTool` (commit/push/PR/branch) | 🟢 repo-local credential isolation |
| plugin tools | ✅ | ✅ Plugins package | ✅ |
| `enclii` CLI (shell-out) | n/a (not their ecosystem) | ⚠️ Only HTTP Switchyard tools | **GAP-2 (PRIORITY):** add `enclii_cli` shell-out |
| `kubectl` (direct) | n/a | ✅ available in worker image, discouraged | ✅ per `feedback_enclii_over_ssh` |
| `gh` CLI | ✅ (indirect via bash) | ⚠️ bash-only | **GAP-3:** add explicit `GhCliTool` wrapper |

### Permission + mode surface

| Capability | claw-code | Selva today | Target / action |
|---|---|---|---|
| Fine-grained permission matrix | ✅ | ✅ 15 `ActionCategory` × 3 `PermissionLevel` | 🟢 richer than claw's single-prompt |
| Permission modes (3 presets) | ✅ `read-only` / `workspace-write` / `danger-full-access` | ❌ | **GAP-4 (PRIORITY):** add `PermissionMode` layer |
| `--allowedTools` runtime allowlist | ✅ | ⚠️ matrix only, no per-call override | **GAP-5:** add `allowed_tools` field on TaskRequest |
| HITL interrupt in-flight | ✅ (CLI prompt) | 🟢 LangGraph `interrupt()` + approval WS | 🟢 async approval, not blocking stdin |
| Approval audit trail | ✅ basic | 🟢 `approval_requests.responded_by` (DB-backed) | 🟢 |
| Tool call stream (visible in UI) | ✅ | 🟢 Ops Feed + events WS + Grafana | 🟢 |

### Provider / model surface

| Capability | claw-code | Selva today | Target / action |
|---|---|---|---|
| Anthropic direct | ✅ | ✅ | ✅ |
| OpenAI-compatible | ✅ | ✅ | ✅ |
| OpenRouter | ✅ | ✅ | ✅ |
| Ollama | ✅ | ✅ | ✅ |
| xAI (Grok) | ✅ | ⚠️ generic OpenAI-compat, no dedicated provider | **GAP-6:** add xAI as first-class (low priority) |
| DashScope (Qwen) | ✅ | ⚠️ via generic OpenAI-compat | **GAP-7:** dashscope prefix routing (low priority) |
| DeepInfra | ❌ | ✅ (bridge mode active as of 2026-04-17) | 🟢 |
| Groq / Together / Fireworks / Mistral / Moonshot / SiliconFlow | ❌ | ✅ registered | 🟢 |
| Model-prefix routing | ✅ (`openai/`, `qwen/`, `gpt-`, `claude`, `grok`) | ⚠️ prefix-aware selection exists but under-documented | **GAP-8:** audit + test prefix routing |
| Short aliases (`opus` / `sonnet` / `haiku`) | ✅ | ⚠️ only task-type aliases (`planning`, `crm`…) | **GAP-9:** add short name aliases in org-config |
| User-defined aliases | ✅ | ✅ (`OrgConfig.aliases` reads YAML) | verify |
| OAuth bearer token | ✅ (`ANTHROPIC_AUTH_TOKEN`) | ⚠️ `ANTHROPIC_API_KEY` only | **GAP-10:** honour bearer token env var (low priority) |
| HTTP proxy (`HTTPS_PROXY` / `NO_PROXY`) | ✅ | ⚠️ httpx default (inherits env, not documented) | **GAP-11:** documentation only |

### CLI / DX surface

| Capability | claw-code | Selva today | Target / action |
|---|---|---|---|
| One-shot prompt CLI | ✅ `claw "..."` | ⚠️ via `autoswarm` Python SDK CLI | **GAP-12:** thin wrapper that makes `autoswarm prompt "..."` work |
| Interactive REPL | ✅ (rustyline) | ⚠️ Office UI only, no terminal REPL | **GAP-13 (P2):** `autoswarm repl` subcommand |
| `--output-format json` | ✅ | 🟢 events WS + REST return JSON | 🟢 |
| Slash commands (`/help`, `/status`, `/cost`, …) | ✅ | ⚠️ Office UI command palette only | **GAP-14 (P3):** parity if/when we ship a terminal REPL |
| **`/doctor` preflight** | ✅ | ❌ | **GAP-15 (PRIORITY):** build doctor |
| `status` / `sandbox` / `agents` / `mcp` / `skills` direct subcommands | ✅ | ✅ via `autoswarm` SDK CLI + HTTP | ✅ |
| `system-prompt --cwd --date` | ✅ | ⚠️ prompts.py builds context but no CLI surface | **GAP-16 (P3):** admin-only endpoint |
| Mock parity harness | ✅ | ⚠️ per-package pytest only | **GAP-17 (P3):** unified scenario harness |
| Config hierarchy | ✅ 5-layer | ✅ org-config + Settings + `.env` | verify precedence documented |
| Sessions under `.claw/sessions/` | ✅ | 🟢 DB-backed via `session_checkpoints` | 🟢 survives process restarts |

---

## Prioritized gap list (this work order)

| # | Gap | Scope | Why priority |
|---|-----|-------|--------------|
| P0 | GAP-2: `enclii` CLI shell-out | small | User explicitly asked. Closes the "binary must just work" contract. |
| P0 | GAP-4: 3-tier permission modes | small | User explicit requirement — no tool-prompt friction outside HITL policy. |
| P0 | GAP-15: `/doctor` preflight | small-medium | Single command to answer "is Selva ready to run the ecosystem?" |
| P1 | GAP-5: `allowed_tools` per-task | small | Sharper blast radius control for experimental pipelines. |
| P1 | GAP-3: `gh` CLI tool | small | GitHub ops today go through bash; wrapping them adds audit + allowlist. |
| P1 | GAP-9: short model aliases | tiny | Ergonomics; trivial change in org-config. |
| P2 | GAP-1, 12, 13, 14: CLI + REPL + resume | medium | DX polish; nice-to-have once server surface is solid. |
| P3 | GAP-6, 7, 10, 11, 16, 17 | medium | Polish + completeness; no operational impact. |

---

## What "absorbed" means going forward

A capability is "absorbed" when it is:

1. **Present in Selva's tool / permission / CLI surface** (via our code, not
   a lift),
2. **Covered by tests** (`packages/tools/tests/`,
   `packages/permissions/tests/`, or equivalent),
3. **Reachable from an autonomous task** dispatched through
   `/v1/swarms/dispatch` without any human tool-approval friction (unless
   the permission matrix specifically says `ASK`),
4. **Documented in** `CLAUDE.md` + this parity doc.

When all four are true, strike the gap off the matrix above.

---

## Related memories + docs

- `memory/feedback_enclii_over_ssh.md` — user prefers `enclii` over kubectl.
- `memory/project_inference_centralization.md` — Selva = inference proxy.
- `memory/project_separation_of_concerns.md` — Selva=inference, Fortuna=intelligence.
- `memory/project_flywheel_bridge_20260417.md` — DeepInfra bridge + shared packages.
- `CLAUDE.md` — this repo's Autonomous Pipeline Security section is
  authoritative for HITL defaults.
