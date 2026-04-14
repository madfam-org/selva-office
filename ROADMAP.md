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

## Immediate Next Steps (Sprint Planning)
1. Configure the **LangGraph Playwright integration** for Phase I (Analyst).
2. Set up the **Celery task worker** for the `/acp/initiate` route to harden the backend execution.

## Q1 Focus: Hive Mind & Continuous Learning (Hermes Integration) ✅

Based on insights from the Hermes Agent architecture, AutoSwarm Office has evolved from executing static paths to a continuous learning ecosystem. All four strategic vectors are now implemented.

### 1. Autonomous Skill Generation (Procedural Memory) ✅
- Phase IV QA Oracle (`acp_qa_oracle.py`) now invokes the `madfam_inference` LLM router when tests pass, instructing an AI model to synthesize validated Phase III logic into a standalone Python `.py` skill conforming to the `PlaybookSkill` interface.
- A stub compiler fallback ensures CI/CD reliability when the LLM router is unavailable.
- Skills are dynamically loaded by the `autoswarm-skills` `SkillRegistry` package at runtime.

### 2. FTS5 SQLite Edge Memory ✅
- `apps/nexus-api/nexus_api/memory_store/db.py` establishes `autoswarm_state.db` with WAL mode and FTS5 virtual tables.
- `insert_transcript()` is called from `/payloads` and `/webhook/qa-oracle` endpoints, permanently archiving all swarm activity for instant full-text recall.

### 3. Serverless Hibernation Tactics ✅
- `EncliiAdapter` extended with `suspend_pod()` and `resume_pod()` to enable scale-to-zero compute posture during idle phases.

### 4. Model Context Protocol (MCP) Capabilities ✅
- `mcp_config.json` declares Tavily search, GitHub, and filesystem tool servers.
- Phase I Analyst RPC subprocess dynamically bootstraps these servers before crawling, enabling tool expansion without container rebuilds.

### 5. Dialectic User Profiling (Honcho) ✅
- `honcho.py` maintains per-operator behavioral profiles stored in EdgeMemoryDB.
- `get_system_addendum(user_id)` injects preference context (verbosity, code style, review strictness) into any LangGraph swarm node's system prompt.

### 6. Multi-Channel Gateway Interfaces ✅
- `apps/nexus-api/nexus_api/routers/gateway.py` provides Telegram and Discord webhook endpoints, enabling operators to trigger ACP workflows directly from messaging apps without UI access.

## Production Readiness Checklist

- `[ ]` Provision `AUTOSWARM_SKILLS_DIR` persistent volume in K8s PVC manifest
- `[ ]` Add `TAVILY_API_KEY` and `GITHUB_TOKEN` to secrets manager for MCP servers
- `[ ]` Register `madfam_inference.get_default_router` singleton with production provider config
- `[ ]` Set Telegram/Discord webhook URLs via `BotFather` / Discord Developer Portal

