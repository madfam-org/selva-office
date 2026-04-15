# Selva Platform — Competitive Benchmark

> Last updated: 2026-04-15 (v0.8.0)

## Unique Position

Selva is the **only platform combining AI agent orchestration with a spatial virtual office**. Competitors are either agent frameworks (no spatial) or virtual offices (no AI).

```
                    AI Agent Sophistication →
                    Low                              High
                ┌──────────────────────────────────────────┐
     High       │  Gather        │           │             │
                │  WorkAdventure │           │  SELVA ★    │
  Spatial /     │  Teamflow      │           │             │
  Virtual       │  SpatialChat   │           │             │
  Office        ├────────────────┼───────────┼─────────────┤
                │                │           │             │
     Low        │                │  CrewAI   │ Hermes      │
                │                │  LangGraph│ OpenClaw    │
                │                │  MS Agent │             │
                └──────────────────────────────────────────┘
```

## Feature Matrix: AI Agent Frameworks

| Capability | **Selva** | Hermes Agent | OpenClaw | CrewAI | LangGraph |
|---|---|---|---|---|---|
| Open source | AGPL-3.0 | MIT | MIT | Apache 2.0 | MIT (lib) |
| Self-hostable | Yes | Yes | Yes | Yes | Lib only |
| Tool count | **54** | 40+ | Community 13.7k | 80+ | Via patterns |
| Graph types | 8 nodes + YAML | Single + sub | Single + routing | 3 processes | Full DAG |
| MCP support | Yes (stdio+HTTP) | Yes | Yes | Yes | Yes |
| Self-improvement | Iterative refiner | Autonomous skills | No | Training | No |
| Skill system | SKILL.md + marketplace | agentskills.io | ClawHub | Dev-defined | Patterns |
| HITL approval | First-class UI | Basic | None | Feedback | First-class |
| Messaging gateways | **18 channels** | 7 | 24+ | None | None |
| Visual workflow builder | **Yes (React Flow)** | No | No | Paid | Paid |
| A2A protocol | **Yes** | No | No | No | No |
| Voice input (STT) | **Yes (Whisper)** | Yes | Yes | No | No |
| Permission engine | RBAC + per-action | None | Broad | Role-based | Planner-locked |
| **Virtual office** | **Yes** | No | No | No | No |

## Feature Matrix: Virtual Office Platforms

| Capability | **Selva** | Gather | WorkAdventure | Teamflow |
|---|---|---|---|---|
| Open source | AGPL-3.0 | No | AGPL + CC | No |
| Self-hostable | Yes | No | Yes | No |
| Spatial audio/video | WebRTC + **LiveKit SFU** | Proprietary | WebRTC + LiveKit | Proprietary |
| Map editor | In-browser + WFC gen | Gather Studio | Tiled (external) | Basic |
| Scripting API | AS.* (sandboxed) | Limited | WA.* (extensive) | No |
| **AI agents** | **Yes (10+ visible)** | No | No | No |
| **Task dispatch** | **Walk to station** | No | No | No |
| **Workflow builder** | **8 node types** | No | No | No |
| Avatar customization | 5 properties | Basic | Basic | Minimal |
| Companions/pets | 5 types | No | No | No |
| Calendar | Google + Microsoft | Google | Google + Outlook | None |
| PWA installable | **Yes** | No | No | No |
| Demo mode | **Yes (8 agents)** | No | No | No |
| Accessible view | **Yes (HTML-only)** | No | No | No |
| Pricing | Self-hosted (free) | $7-22/user/mo | Free-10€/user/mo | $15/mo+ |

## Parity Scorecard

| Platform | Parity | Key Advantage Selva Has |
|---|---|---|
| Hermes Agent | **95%** | Virtual office, visual builder, 18 gateways, HITL UI, A2A |
| OpenClaw | **90%** | Permission engine, zero CVEs, HITL, virtual office |
| Gather | **100%+** | AI agents, workflow builder, self-hosting, free |
| WorkAdventure | **100%+** | AI agents, learning loop, 54 tools, A2A, voice |
| CrewAI | **92%** | Visual builder (free), 18 gateways, spatial office, A2A |
| LangGraph | **95%** | Virtual office, voice, A2A, spatial presence |
| MS Agent Framework | **85%** | A2A compat, virtual office, all other features |

## Platform Stats (v0.8.0)

| Metric | Value |
|---|---|
| Total LOC | ~35,000+ |
| Source files | ~820 |
| Test suites | 90+ |
| Total tests | 800+ |
| Built-in tools | 54 |
| Graph node types | 8 |
| Messaging gateways | 18 |
| Alembic migrations | 15 (0000-0014) |
| API routes | 128+ |
| Packages | 10 (inference, workflows, skills, tools, memory, orchestrator, calendar, permissions, redis-pool, a2a) |

## Security Posture

| Metric | Selva | OpenClaw | Hermes |
|---|---|---|---|
| CVEs | 0 | 9 (March 2026) | 0 |
| SSRF protection | All webhooks + HTTP tools | None | N/A |
| SQL injection prevention | Query type validation | N/A | N/A |
| Permission engine | RBAC matrix + per-action | Broad default | None |
| CSRF protection | Double-submit cookie | N/A | N/A |
| Malicious skills | 0 reported | ~900 in ClawHub | 0 reported |
