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

## Q1 Focus: Hive Mind & Continuous Learning (Hermes Integration)

Based on insights from the Hermes Agent architecture, AutoSwarm Office will evolve from executing static paths to a continuous learning ecosystem.

### 1. Autonomous Skill Generation (Procedural Memory)
- Develop an evaluation and synthesis loop where Clean Swarms monitor successful QA Oracle test passes.
- Automatically compress these complex problem-solving trajectories into standard Python scripts (`.py` files) stored as persistent "Skills".
- Allow future swarms to dynamically load these standard playbooks through a central `autoswarm-skills` registry.

### 2. FTS5 SQLite Edge Memory
- Establish a `state.db` storage backend in `apps/nexus-api/` using SQLite in WAL mode.
- Implement FTS5 virtual tables to allow human operators and Swarms sub-millisecond semantic text search across thousands of historically isolated execution transcripts without the latency or overhead of external vector stores.

### 3. Serverless Hibernation Tactics
- Refactor the `EncliiAdapter` lifecycle behavior. 
- Instead of treating Enclii clusters as strictly binary (deploy or teardown), introduce `suspend` and `resume` lifecycle logic to scale-to-zero compute overhead when pods are idling.

### 4. Model Context Protocol (MCP) Capabilities
- Enhance the Analyst Swarm tool sets by natively utilizing standard `mcp` servers, establishing dynamic tool adoption across isolated execution pods.
