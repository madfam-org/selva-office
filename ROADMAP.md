# AutoSwarm Office: Product Roadmap

This document outlines the strategic priorities and upcoming milestones for the `autoswarm-office` platform.

## Q3/Q4 Focus: Autonomous Cleanroom Protocol (ACP)

The core architectural scaffolding for the Autonomous Cleanroom Protocol has been merged (see `docs/AUTONOMOUS_CLEANROOM_PROTOCOL.md`). The following are the remaining milestones required to transition this system from structural stubs to a fully functional, production-ready feature.

### 1. LangGraph Execution Engine Upgrade (High Priority/Immediate)
The four workflow nodes currently exist as structural class stubs. We must implement proper `CompiledGraph` execution:
- **Phase I (Analyst)**: Hook up Playwright/Selenium integration to allow headless browsing and PRD generation.
- **Phase II (Sanitizer)**: Implement regex pipelines and strict negative-constraint LLM chains to ensure no proprietary variables leak.
- **Phase III (Clean Swarm)**: Inject "Divergent Thinking" system prompts into the coding engine constraints.
- **Phase IV (QA Oracle)**: Build the dynamic test runner capable of safely executing PyTest/Jest against Phase III output in the sandbox.

### 2. Event-Driven Orchestration
- Migrate the Nexus API ACP trigger (`/acp/initiate`) from FastAPI `BackgroundTasks` to a durable task queue mechanism (Celery + Redis) to ensure the multi-hour workflow survives API pod restarts.

### 3. Airgap Data Handoff Pipeline
- Replace the current raw JSON payload handoff.
- Establish a secure intermediary storage mechanism (e.g., temporary MinIO/S3 bucket) where Nexus API deposits the sanitized PRD, allowing the Clean Swarm to volume-mount and read it without compromising its strict egress network isolation.

### 4. Enclii Production API Integration
- Upgrade `enclii_adapter.py` by uncommenting `httpx` methods and adding robust error handling/connection retries.
- Implement cryptographic webhook secrets dynamically injected into Enclii pods to secure the Phase IV return (`/webhook/qa-oracle`).

### 5. ACP Test Suite
- **Unit Tests**: Validate the Sanitizer's deterministic parser perfectly catches known proprietary IP terminology.
- **Integration Tests**: Mock the Enclii API to verify that the Nexus API successfully requests pod creation, manages the network lifecycle, and handles the Phase IV webhook logic.

## Immediate Next Steps (Sprint Planning) ✅
1. Configure the **LangGraph Playwright integration** for Phase I (Analyst). ✅
2. Set up the **Celery task worker** for the `/acp/initiate` route to harden the backend execution. ✅

---

## Q1 Focus: Hive Mind & Continuous Learning (Hermes Integration) ✅

Based on insights from the Hermes Agent architecture, AutoSwarm Office has evolved from executing static paths to a continuous learning ecosystem. All six strategic vectors are now implemented.

### 1. Autonomous Skill Generation (Procedural Memory) ✅
- Implemented in `acp_qa_oracle.py`. Synthesizes validated Phase III logic into `.py` skills.
- Supported by `SkillMDRegistry` for progressive disclosure.

### 2. FTS5 SQLite Edge Memory ✅
- `autoswarm_state.db` established with WAL/FTS5. Memory compaction via Celery Beat implemented.

### 3. Serverless Hibernation Tactics ✅
- `EncliiAdapter` extended with scale-to-zero capabilities.

### 4. Model Context Protocol (MCP) Capabilities ✅
- Dynamic bootstrap of Tavily, GitHub, and filesystem tool servers.

### 5. Dialectic User Profiling (Honcho) ✅
- `HonchoProfiler` maintains behavioral profiles in EdgeMemoryDB.

### 6. Multi-Channel Gateway Interfaces ✅
- 18 platforms supported (Telegram, Discord, Slack, WhatsApp, Matrix, Signal, etc.).

---

## Q2 Focus: Hermes Gap Remediation — Full Autonomous Intelligence ✅

All 8 architectural gaps identified in the Hermes Agent parity benchmark have been remediated across Waves 1–4.

### Wave 1: Core Parity ✅
- Skill Refiner, Memory Compactor, Cron Scheduler, Slack/Email/SMS gateways.

### Wave 2 & 3: Runtime Maturity ✅
- Browser/Vision tooling (Playwright).
- Dangerous command approval gate (HITL).
- Plugin Architecture (3-source discovery).
- Prompt Caching & Context Compression.
- Session Checkpoints & Rollback.
- SOUL.md Personality Injection.

### Wave 4: Tool & Platform Breadth ✅
- **23 New Tools**: `execute_code`, `file_tools`, `web_tools`, `process_registry`, `media_tools` (Image Gen, TTS).
- **18 Gateway Platforms**: Complete parity with Hermes Agent messaging stack.
- **Skills Hub**: REST client for `agentskills.io` for community skill sharing.
- **Developer Experience**: Interactive Setup Wizard CLI + ACP JSON-RPC server shell.

---

## Q3 Focus: The Final Frontier — Industrial Grade Integration

While horizontal parity is achieved, deep vertical integration for professional research and enterprise workflows remains.

### 1. Specialized Execution Backends 🟠
- Implement **SSH Terminal Backend** for remote node control.
- Add **Modal / Daytona / Singularity** support for research-heavy workloads.
- Standardize **Docker socket mounting** for the `execute_code` sandbox.

### 2. Deep IDE Experience 🟠
- Transition the ACP Server from a shell to a **full JSON-RPC protocol implementation**.
- Develop a **VS Code / Zed Extension** to provide a native UI for the ACP server.

### 3. Audio & Voice Mode 🟠
- Implement **STT (Speech-to-Text)** via Whisper/Vosk to enable full duplex voice interaction (mirroring Hermes voice mode).

### 4. RL & Training Loops 🟠
- Direct **Atropos Integration** for automated agent evaluation.
- Implement the **Closing the Loop** training harness to fine-tune models on exported trajectories.

---

## Competitive Dominance Roadmap

### Wave 1: Quick Wins (v0.6.0) ✅
- `[x]` Screen sharing polish — quality presets + system audio capture
- `[x]` Iterative skill refinement — refine→validate→retry loop + metrics API
- `[x]` PWA installable — manifest, service worker, icons, apple-mobile-web-app

### Wave 2: Strategic (v0.7.0) ✅
- `[x]` Voice mode (STT): SpeechToTextTool + /api/v1/voice/transcribe + meeting graph integration
- `[x]` LiveKit SFU: hybrid P2P/SFU with auto-threshold switching + livekit-server Docker service

### Wave 3: Ecosystem (Planned)
- `[ ]` **Tool expansion to 60+**: Email, database, HTTP, document, analytics tool categories
- `[ ]` **A2A protocol**: Agent-to-Agent interop (AgentCard, task send/subscribe, discovery)

### Wave 4: Polish (Planned)
- `[ ]` **Mobile UX**: Haptic feedback, compact touch layout, bottom tab bar
- `[ ]` **Benchmark docs**: Competitive metrics dashboard (BENCHMARK.md)

---

## Selva Brand Migration Checklist

- `[x]` Rename all `*.madfam.io` domains → `*.selva.town` in codebase
- `[x]` Rename Python package `madfam-inference` → `selva-inference`
- `[x]` Update brand text (MADFAM → Selva) across UI, docs, skills, prompts
- `[x]` Rename Docker network, npm scope, seed scripts, community skills
- `[ ]` **Email routing**: Configure Cloudflare Email Routing on `selva.town` zone
  - Catch-all `*@selva.town` → `admin@madfam.io`
  - Covers: `noreply@selva.town` (transactional), `engineering@selva.town` (package metadata)
  - Enable in Cloudflare Dashboard → Email → Email Routing → Routing Rules
- `[ ]` Provision DNS records for `selva.town` (A/CNAME for agents-api, agents, agents-ws, auth, etc.)
- `[ ]` Update Cloudflare Tunnel routes to serve `*.selva.town` hostnames
- `[ ]` Migrate GitHub org `madfam-org` → new org name (deferred — update ghcr.io refs after)
- `[ ]` Update npm registry URL if migrating from `npm.madfam.io` to `npm.selva.town`
- `[ ]` Set up `selva.town/terms` and `selva.town/privacy` landing pages

## Production Readiness Checklist

- `[x]` Provision `AUTOSWARM_SKILLS_DIR` persistent volume in K8s
- `[ ]` Inject Wave 3/4 Gateway secrets (DingTalk, Feishu, BlueBubbles, HA, etc.)
- `[x]` Add `TAVILY_API_KEY` and `OPENAI_API_KEY` to worker pods
- `[x]` Run `alembic upgrade head` to apply checkpoint/approval tables (migrations 0000-0014)
- `[ ]` Map local Docker socket to Celery worker pods for sandboxing
- `[x]` Fix auth exports (`CurrentUser`, `require_roles`) for Wave 4 routers
- `[x]` Add Wave 4 ORM models (`Schedule`, `CommandApprovalRequest`) to `models.py`
- `[x]` Fix worker test mock signatures (emit_event + **kwargs)
- `[x]` Auto-fix 323 Python lint errors (ruff --fix)
- `[x]` Add gateway service to docker-compose.yml
- `[x]` Document `NEXUS_API_URL`, `NEXUS_API_WS_URL`, `GATEWAY_HEALTH_PORT` in .env.example


