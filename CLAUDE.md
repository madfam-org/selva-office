# CLAUDE.md -- AutoSwarm Office

## Quick Start (Local Dev)

```bash
# Prerequisites: Docker, Node 20+, pnpm 9+, Python 3.12+, uv

# 1. Clone and install
git clone <repo-url>
cd autoswarm-office
make dev-full    # Installs deps, starts Docker, migrates, seeds, boots all services

# 2. Open the office
# Navigate to http://localhost:4301
# Click "Dev Login (bypass)"

# 3. (Optional) Enable LLM inference
# Add at least one API key to .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   or OPENAI_API_KEY=sk-...
# Then restart the worker: make worker

# 4. (Optional) Enable git push
# Set GITHUB_TOKEN in .env to a PAT with repo scope
```

## Critical Paths

- `apps/nexus-api/src/main.py` -- FastAPI application entry point
- `apps/office-ui/src/app/page.tsx` -- Office UI root page
- `apps/workers/autoswarm_workers/__main__.py` -- Worker process entry (task status lifecycle)
- `apps/workers/autoswarm_workers/task_status.py` -- Fire-and-forget task PATCH to nexus-api
- `apps/workers/autoswarm_workers/auth.py` -- Centralized worker-to-API auth headers
- `apps/workers/autoswarm_workers/prompts.py` -- Repo-context-aware LLM system prompts
- `apps/workers/autoswarm_workers/learning.py` -- Post-task learning (experience, reflexion, bandit, stats)
- `apps/workers/autoswarm_workers/event_emitter.py` -- Fire-and-forget event POST + Redis PUBLISH
- `apps/nexus-api/nexus_api/routers/events.py` -- Events REST API + WebSocket stream
- `apps/nexus-api/nexus_api/routers/metrics.py` -- Ops metrics dashboard aggregation API
- `apps/workers/autoswarm_workers/graphs/coding.py` -- Coding graph (plan/implement/test/review/push)
- `apps/workers/autoswarm_workers/graphs/base.py` -- Shared graph state, permission checks
- `packages/orchestrator/src/orchestrator.py` -- Swarm orchestration engine
- `packages/permissions/src/matrix.py` -- HITL permission matrix
- `packages/permissions/src/engine.py` -- Permission evaluation engine
- `packages/inference/madfam_inference/org_config.py` -- Org-level config (task types, model assignments)
- `packages/inference/madfam_inference/router.py` -- LLM model routing logic
- `apps/nexus-api/nexus_api/routers/intelligence.py` -- Intelligence config API
- `apps/nexus-api/nexus_api/routers/chat.py` -- Chat history persistence API
- `apps/nexus-api/nexus_api/routers/admin.py` -- Admin controls (kick, room config)
- `apps/colyseus/src/handlers/teleport.ts` -- Player teleport handler
- `packages/workflows/src/autoswarm_workflows/compiler.py` -- YAML-to-LangGraph compiler
- `packages/workflows/src/autoswarm_workflows/schema.py` -- Workflow definition models
- `packages/tools/src/autoswarm_tools/registry.py` -- Tool registry (24 built-in tools)
- `packages/memory/src/autoswarm_memory/store.py` -- Per-agent FAISS memory store
- `packages/tools/src/autoswarm_tools/storage/local.py` -- Content-addressable artifact storage
- `packages/tools/src/autoswarm_tools/builtins/artifact.py` -- Artifact management tools (save/retrieve/list)
- `packages/workflows/src/autoswarm_workflows/nodes/batch.py` -- Batch processing node handler
- `packages/tools/src/autoswarm_tools/builtins/image_analysis.py` -- Image analysis tool (multimodal)
- `apps/nexus-api/nexus_api/routers/marketplace.py` -- Skill marketplace CRUD API
- `packages/sdk/autoswarm_sdk/client.py` -- Python SDK async/sync clients
- `packages/orchestrator/autoswarm_orchestrator/bandit.py` -- Thompson Sampling agent selection
- `packages/orchestrator/autoswarm_orchestrator/puppeteer.py` -- RL orchestrator
- `apps/workers/autoswarm_workers/graphs/puppeteer.py` -- Puppeteer graph (decompose/assign/execute/aggregate/feedback)
- `apps/workers/autoswarm_workers/graphs/meeting.py` -- Meeting notes graph (transcribe/summarize/extract/save)
- `packages/calendar/autoswarm_calendar/` -- Google/Microsoft calendar adapters
- `apps/nexus-api/nexus_api/routers/maps.py` -- Map CRUD API
- `apps/nexus-api/nexus_api/routers/calendar.py` -- Calendar connection API

## Production Hardening (v0.3.0)

- **Worker Concurrency**: `MAX_CONCURRENT_TASKS` env var (default 3). Semaphore-bounded
  `asyncio.create_task()` with graceful shutdown drain.
- **LLM JSON Retry**: `implement()` retries LLM up to 2 times on `JSONDecodeError`,
  re-prompting with error context. Returns `status: "error"` on exhaustion (not
  placeholder). Conditional edge `implement → END` when `status == "error"`.
- **Git Credential Isolation**: `BashTool.execute()` accepts `env` kwarg. Token passed
  to `create_pr()` via subprocess env instead of `os.environ`.
- **Worktree Cleanup**: `_cleanup_stale_worktrees()` runs on startup, removes
  worktrees older than `WORKTREE_STALE_HOURS` (default 24).
- **Dispatch Rate Limiting**: Per-user sliding window via `MessageRateLimiter` on
  `POST /dispatch` (default 10 req/60s). Config: `DISPATCH_RATE_LIMIT`,
  `DISPATCH_RATE_WINDOW`.
- **BashTool Sandbox**: Blocks `cd ..` when `allowed_cwd` is set.
- **Approval Polling Jitter**: `poll_interval * (0.5 + random())` to avoid
  thundering herd.
- **DLQ Monitoring**: `GET /api/v1/health/dlq-stats` returns depth and recent entries.
- **Stale Task Reaper**: `POST /api/v1/swarms/tasks/reap-stale` auto-fails
  queued/pending tasks older than 1 hour.
- **Inference Retry + Fallback**: `ModelRouter.complete()` retries primary once (1s
  delay), then falls through to alternative providers.
- **Approval Audit Trail**: `responded_by` column on `approval_requests` (migration
  0012). Populated from JWT `sub` claim.
- **Git Identity**: `GitTool.configure_identity()` sets repo-local `user.name` /
  `user.email` before every agent commit. Config: `GIT_AUTHOR_NAME` (default
  `autoswarm-bot`), `GIT_AUTHOR_EMAIL` (default `bot@autoswarm.dev`).
- **Worker-to-API Auth**: Centralized via `auth.py:get_worker_auth_headers()`.
  Reads `WORKER_API_TOKEN` env var (default `dev-bypass`). Used by
  `task_status.py`, `event_emitter.py`, `interrupt_handler.py`, and
  `__main__.py:_fetch_agent_skills()`. No hardcoded tokens in source.
- **CSRF Exemptions**: `/api/v1/events`, `/api/v1/approvals`, `/api/v1/billing/`,
  `/api/v1/swarms/tasks/` added to CSRF exempt prefixes (worker-to-API calls).
- **PR Creation Compat**: `GitTool.create_pr()` resolves `OWNER/REPO` from git
  remote URL and uses `--repo` flag instead of `-C` (compat with older `gh` CLI).
- **Worktree Branch Naming**: `plan()` creates worktree with branch
  `autoswarm/task-{id}` (was `task-{id}`) to match `push_gate()` expectations.

## Agent Learning Loop (v0.4.0)

- **Experience Recording**: `learning.py:record_experience()` stores task outcomes
  in `ExperienceStore` (per-role, 30-day temporal decay) and `MemoryStore`
  (per-agent). Score mapping: completed=1.0, denied=0.2, failed=0.0. Fire-and-forget.
- **Reflexion**: `learning.py:generate_reflexion()` calls LLM for self-critique on
  failures (Reflexion NeurIPS 2023 pattern). Falls back to basic text when LLM
  unavailable. Stored with score=0.3 and `metadata.type="reflection"`.
- **Experience Injection**: `prompts.py:build_experience_context()` retrieves
  similar past experiences and agent memories, injecting them into plan/implement/
  review prompts. Graceful degradation to empty string on any error.
- **Agent Performance Tracking**: 6 columns on `Agent` model (`tasks_completed`,
  `tasks_failed`, `approval_success_count`, `approval_denial_count`,
  `avg_task_duration_seconds`, `last_task_at`). `PATCH /api/v1/agents/{id}/stats`
  accepts delta increments with running average for duration. Migration `0013`.
- **Bandit Reward**: `learning.py:update_bandit_reward()` updates `ThompsonBandit`
  after every task (not just puppeteer). Reward: 1.0 (success), 0.2 (partial), 0.0
  (failure). Persisted to `BANDIT_PERSIST_PATH`.
- **Performance-Aware Dispatch**: Skill-based agent matching in `swarms.py` weighted
  by `_compute_perf_weight()` (30% performance, 70% skill overlap). New agents
  default to 0.5 (neutral). `perf_weight = 0.5 * approval_rate + 0.5 * completion_rate`.
- **Config**: `MEMORY_PERSIST_DIR` (default `/tmp/autoswarm-memory`),
  `BANDIT_PERSIST_PATH` (default `/tmp/autoswarm-bandit.json`).
- **CSRF**: `/api/v1/agents/` stats endpoint uses Bearer auth which bypasses CSRF.

## Autonomous Dev Readiness (v0.3.1)

- **test() Node Fix**: `test()` uses `_run_async()` instead of
  `asyncio.get_event_loop()`, which crashed in ThreadPoolExecutor threads.
- **Worker Auth Hardening**: `WORKER_API_TOKEN` env var (default `dev-bypass`).
  `auth.py:get_worker_auth_headers()` centralizes all worker-to-API auth.
  No hardcoded `"Bearer dev-bypass"` in source files.
- **Org Config Bootstrap**: `make setup-org-config` copies
  `data/org-config-template.yaml` to `~/.autoswarm/org-config.yaml`. Wired
  into `make dev-full`. Worker logs warning when org config missing.
- **Enhanced System Prompts**: `prompts.py` provides `build_plan_prompt()`,
  `build_implement_prompt()`, `build_review_prompt()` with repo context
  (top-level listing, README excerpt, CLAUDE.md conventions, language
  detection). Strict JSON format instructions prevent LLM returning
  markdown instead of file objects.
- **Docker Compose Compat**: `DOCKER_COMPOSE` Makefile variable auto-detects
  `docker-compose` (v1) vs `docker compose` (v2 plugin).

## Port Assignments

| Port | Service | Notes |
|------|---------|-------|
| 4300 | nexus-api | Central API |
| 4301 | office-ui | Next.js frontend |
| 4302 | admin | Admin dashboard |
| 4303 | colyseus | Game state server |
| 4304 | gateway | Heartbeat daemon (health + metrics HTTP) |
| 4305 | workers | Worker health + metrics HTTP server |

These ports do not conflict with Janua (4100-4104) or Enclii (4200-4204).

## Commands

```bash
make dev              # Start all services (TS + Python + Worker)
make dev-full         # Full boot: Docker + migrations + all services
make dev-seed         # Seed departments and agents (requires nexus-api running)
make worker           # Run worker process independently
make test             # Run all tests
make lint             # Run all linters
make typecheck        # TypeScript + mypy
make build            # Build all packages
make docker-dev       # Start Postgres + Redis
make db-migrate       # Run Alembic migrations
make db-seed          # Seed departments and agents
make smoke-test       # Verify all services are healthy
make generate-assets  # Regenerate pixel-art sprite PNGs
make generate-variants # Generate palette-themed sprite/tile variants
make generate-map     # Procedurally generate office map (WFC)
make generate-office-map  # Generate hand-crafted 50x28 office map
make post-process     # Optional ImageMagick upscale/WebP conversion
make db-backup        # Backup PostgreSQL database
make db-restore       # Restore from backup (BACKUP_FILE=<path>)
make db-verify-backup # Verify backup integrity (BACKUP_FILE=<path>)
make worktree-cleanup # Remove stale git worktrees (STALE_HOURS=24)
make setup-org-config # Bootstrap ~/.autoswarm/org-config.yaml from template

pnpm dev              # TypeScript services only
pnpm build            # Build TypeScript packages
pnpm lint             # ESLint
pnpm test             # TypeScript tests (660+ tests across 55+ suites)
pnpm typecheck        # TypeScript type checking

uv run pytest packages/ apps/nexus-api/  # Python tests (670+ tests)
uv run pytest apps/workers/tests/       # Worker tests (140+ tests)
uv run ruff check .   # Python linting
uv run mypy .         # Python type checking
```

## MADFAM Ecosystem

- **Janua** handles all authentication. Never implement custom auth. Use the
  `get_current_user` dependency in FastAPI and the Next.js middleware for session
  validation. Janua tokens are JWTs with `sub`, `email`, `roles`, and `org_id` claims.

- **Dhanam** handles billing and subscriptions. Compute token budgets are enforced
  by the orchestrator package and tracked in the `compute_token_ledger` table.
  Use the billing router at `apps/nexus-api/src/routers/billing.py`.

- **Enclii** handles deployment. The `.enclii.yml` defines all three services.
  The `deploy-enclii.yml` GitHub Actions workflow builds images and notifies Enclii.

- Read sibling repo `llms-full.txt` files for full API surfaces of Janua, Dhanam,
  and Enclii.

## Coding Standards

### Python
- **Linter**: ruff (target py312, line-length 100)
- **Type checker**: mypy (strict mode)
- **Models**: pydantic for all request/response schemas
- **ORM**: SQLAlchemy with async sessions
- **Tests**: pytest with pytest-asyncio
- **Imports**: isort via ruff, `autoswarm` as known-first-party

### TypeScript
- **Strict mode**: enabled in all tsconfig.json files
- **Linter**: ESLint with shared config from `packages/config/eslint`
- **Formatter**: Prettier
- **Tests**: vitest with jsdom + @testing-library/react for UI components
- **Build**: Turborepo for monorepo orchestration
- **Package manager**: pnpm with workspace protocol

## Git Workflow

- Feature branches only -- never commit directly to `main`.
- Conventional commits enforced by commitlint:
  `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `perf`
- PRs require CI to pass before merge.

## Skills System

The `packages/skills/` package implements the AgentSkills standard.

- **Core skills** (10) live in `packages/skills/skill-definitions/`. Always loaded.
- **Community skills** (~25) live in `packages/skills/community-skills/`. Vendored from
  [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills).
  Disabled by default.
- `SkillTier` enum: `CORE` | `COMMUNITY`. Set by the registry during discovery, not
  from YAML frontmatter.
- Enable community skills via:
  - Env var: `AUTOSWARM_COMMUNITY_SKILLS_ENABLED=true`
  - Runtime: `get_skill_registry().enable_community_skills()`
  - REST API: `POST /api/v1/skills/community/enable`
- Core skills always take precedence on name collision with community skills.
- Community skill scripts under `community-skills/` are excluded from ruff linting
  via `extend-exclude` in `pyproject.toml`.

## Dynamic Workflow System (ChatDev 2.0 Parity)

### Workflow Engine (`packages/workflows`)
- **Schema** (`schema.py`): Pydantic models for `WorkflowDefinition`, `NodeDefinition`
  (8 node types: `agent`, `human`, `passthrough`, `subgraph`, `python_runner`,
  `literal`, `loop_counter`, `batch`), `EdgeDefinition` with conditional routing.
- **Compiler** (`compiler.py`): `WorkflowCompiler.compile(workflow_def)` → LangGraph
  `StateGraph`. Supports conditional edges (regex, keyword, expression), context
  window policies (keep_all, keep_last_n, clear_all, sliding_window), and subgraph
  nesting via recursive compilation.
- **Serializer** (`serializer.py`): YAML ↔ WorkflowDefinition roundtrip.
- **Validator** (`validator.py`): Cycle detection (loop counter nodes exempt),
  orphan node warnings, edge reference checks, type-specific config validation.
- Custom workflows dispatched via `graph_type: "custom"` + `workflow_id` in
  `POST /api/v1/swarms/dispatch`. YAML loaded from `workflows` table, compiled
  at runtime by the worker.

### Tool Registry (`packages/tools`)
- **BaseTool** ABC with `name`, `description`, `parameters_schema()`, `async execute()`.
- `ToolRegistry` singleton: 23 built-in tools across 8 categories (file ops, code
  exec, git, web, data, communication, environment, artifacts). `get_specs(tool_names)` returns
  OpenAI function-calling format.
- **MCP Client** (`mcp/client.py`): `McpToolAdapter` wraps remote MCP tools as
  BaseTool instances. Stdio and HTTP transports. `discover_mcp_tools(transport)`
  auto-registers.

### Agent Memory (`packages/memory`)
- **MemoryStore**: Per-agent FAISS `IndexFlatIP` with metadata. `store()`, `search()`,
  `list_entries()`, `delete()`. Persists to disk (index.faiss + entries.json).
- **EmbeddingProvider**: OpenAI (`text-embedding-3-small`), Ollama
  (`nomic-embed-text`), or hash-based fallback for dev.
- **ExperienceStore** (IER): Per-role task pattern learning with temporal decay
  (30-day half-life). `record()`, `search_similar()`, `get_shortcuts()`.
- **MemoryManager**: Lazy-loading per-agent stores, `get_relevant_context()` for
  LLM prompt injection.

### Workflow CRUD API
- `POST/GET/PUT/DELETE /api/v1/workflows` + `/validate`, `/import`, `/export`
- Alembic migration `0005` adds `workflows` table + `workflow_id` FK on `swarm_tasks`

### Visual Workflow Builder (Phase 4)
- **Blueprint Room**: `dept-blueprint` department zone (maxAgents: 0) at (800,260).
  `blueprint` interactable type emits `open_blueprint` event → opens WorkflowEditor.
- **WorkflowEditor** (`apps/office-ui/src/components/workflow-editor/`): Full-screen
  modal with React Flow canvas, 8 custom node types (Agent, Human, Passthrough,
  Subgraph, PythonRunner, Literal, LoopCounter, Batch), conditional edges, NodePalette
  (drag-and-drop), PropertiesPanel (dynamic form fields), EditorToolbar (New, Save,
  Load, Export YAML, Import YAML, Validate, Run).
- **workflow-converter** (`apps/office-ui/src/lib/workflow-converter.ts`): Bidirectional
  YAML ↔ React Flow conversion. Preserves node positions in `position_x`/`position_y`.
- **useWorkflow hook**: State machine (idle|loading|saving|validating|error) for
  workflow CRUD operations via `/api/v1/workflows` API.
- **Execution monitoring**: `AgentSchema.currentNodeId` (Colyseus) synced via Redis
  pub/sub from worker `_publish_agent_status(current_node_id=...)`. Active nodes
  highlighted in editor canvas. `[nodeId]` label rendered under agent sprites in
  OfficeScene. `ExecutionLog` panel shows chronological events.
- **Custom workflow dispatch**: `graph_type: 'custom'` + `workflow_id` in
  `POST /api/v1/swarms/dispatch`. Worker uses `compiled.astream()` for node-level
  progress streaming via `_run_custom_with_streaming()`.
- **Shared types**: `packages/shared-types/src/workflow.ts` mirrors Python schema.
  `Agent.currentNodeId` optional field.
- **Dependencies**: `@xyflow/react`, `js-yaml` (office-ui).

### Phase 5: Advanced Features

#### Artifact Management (5.1)
- **Storage**: `packages/tools/src/autoswarm_tools/storage/` — `ArtifactStorage` ABC +
  `LocalFSStorage` (content-addressable SHA-256 dedup, layout `<hash[:2]>/<hash[2:4]>/<hash>`).
  `ARTIFACT_STORAGE_PATH` env var or `/tmp/autoswarm-artifacts` default.
- **Tools**: `SaveArtifactTool`, `RetrieveArtifactTool`, `ListArtifactsTool` in
  `builtins/artifact.py`. Registered in `get_builtin_tools()`.
- **REST API**: `apps/nexus-api/nexus_api/routers/artifacts.py` —
  `GET /api/v1/artifacts`, `GET .../download`, `DELETE ...`. Org-scoped.
- **DB**: `Artifact` model in `models.py`, migration `0006_add_artifacts_table`.

#### Batch Processing Node (5.2)
- **Schema**: `NodeType.BATCH` + `BatchAggregateStrategy` enum (`collect`/`merge`/`vote`).
  `NodeDefinition` extended with `batch_split_key`, `batch_aggregate_strategy`,
  `max_parallel`, `delegate_node_id`.
- **Handler**: `BatchNodeHandler` in `nodes/batch.py` — splits `state[split_key]`,
  runs delegate function in parallel via `asyncio.Semaphore`, aggregates per strategy.
- **Compiler**: batch nodes exempt from cycle detection (like loop_counter).
  Delegate functions wired after all nodes are built.
- **Validator**: checks `MISSING_BATCH_SPLIT_KEY`, `MISSING_BATCH_DELEGATE`,
  `INVALID_BATCH_DELEGATE`.
- **UI**: `BatchNode` React Flow component, palette entry, PropertiesPanel fields.

#### Multimodal Inference (5.3)
- **Types**: `ContentType` enum (TEXT/IMAGE_URL/IMAGE_BASE64), `MediaContent` model
  in `packages/inference/madfam_inference/types.py`. `InferenceRequest.messages`
  accepts `list[dict[str, Any]]` for multimodal content blocks. `has_media()` helper.
- **Provider vision**: `InferenceProvider.supports_vision` property (default False).
  OpenAI, Anthropic, Ollama, Generic providers all support vision with
  `_format_messages()` converting to native multimodal formats.
- **Router**: Vision-aware provider selection — filters to `supports_vision=True`
  providers when `request.has_media()`.
- **Open-source providers**: Together AI, Fireworks AI, DeepInfra registered as
  `GenericOpenAIProvider` instances in worker `build_model_router()`. Config fields
  in both worker and nexus-api Settings. `CLOUD_PRIORITY` and `CHEAPEST_PRIORITY`
  updated (deepinfra cheapest, anthropic highest quality).
- **ImageAnalysisTool**: `builtins/image_analysis.py` — constructs multimodal
  messages with image + prompt, returns `requires_inference: True` for worker dispatch.
- **Tool count**: 24 built-in tools (was 23).

#### Skill Marketplace (5.4)
- **DB**: `SkillMarketplaceEntry` and `SkillRating` models in `models.py`.
  Migration `0007_add_skill_marketplace` creates both tables with FK CASCADE,
  unique constraint on `(entry_id, user_id)`.
- **REST API**: `routers/marketplace.py` — `GET/POST/DELETE /api/v1/marketplace/skills`,
  `POST .../rate`, `POST .../install`. Search, category filter, sort by
  downloads/rating/newest. Install writes SKILL.md to `community-skills/` and
  calls `registry.refresh()`.
- **Registry**: `SkillRegistry.refresh()` clears caches and re-discovers skills.
  `parse_skill_md_string()` validates YAML from raw strings (marketplace publish).
- **UI**: `SkillMarketplace.tsx` full-screen modal with search, category tabs,
  sort, 2-column card grid, detail view with readme/YAML preview/rating form.
  `useMarketplace` hook (state machine). Accessed via "Skills" button in
  DashboardPanel header.

### Python SDK (`packages/sdk`)
- **AutoSwarm** async client: `dispatch()`, `list_agents()`, `get_task()`,
  `wait_for_task()`. Uses `httpx.AsyncClient` with Bearer auth.
- **AutoSwarmSync**: synchronous wrapper using `asyncio.run()`.
- **CLI**: `autoswarm dispatch "desc" --graph-type coding`, `autoswarm agents list`,
  `autoswarm tasks get <id>`, `autoswarm tasks wait <id>`. Click-based.
  Reads `AUTOSWARM_API_URL` and `AUTOSWARM_TOKEN` env vars.
- **Exceptions**: `AutoSwarmError`, `AuthenticationError`, `TaskTimeoutError`,
  `NotFoundError` with `status_code` attribute.

### Workflow Templates (`data/workflow-templates/`)
- 5 domain YAML templates: `3d-modeling`, `video-production`, `data-analysis`,
  `devops-pipeline`, `content-marketing`. Each includes `loop_counter` nodes
  for cycle-safe review loops.
- **API**: `GET /api/v1/workflows/templates` lists templates,
  `POST /api/v1/workflows/from-template` creates a Workflow from a template.
- **UI**: `TemplateGallery.tsx` full-screen modal with category filter tabs
  (All/Development/Creative/Data/Operations), card grid, and preview.
  Opened via "Templates" button in `EditorToolbar`.

### RL Orchestration / Puppeteer Mode
- **ThompsonBandit** (`packages/orchestrator`): Beta distribution multi-armed
  bandit with `select(candidates)`, `update(agent_id, reward)`, and JSON
  file persistence.
- **PuppeteerOrchestrator**: Extends `SwarmOrchestrator` with bandit-based
  `select_agent()` and `select_agents()` (without replacement).
- **Puppeteer graph** (`apps/workers/graphs/puppeteer.py`):
  `decompose` → `assign` (bandit) → `execute_parallel` (semaphore) →
  `aggregate` → `feedback` → END. Graph type: `"puppeteer"`, timeout: 600s.

### Whiteboards
- **Schema**: `StrokeSchema` (x, y, toX, toY, color, width, tool, senderId) +
  `WhiteboardSchema` (id, strokes ArraySchema). Part of `OfficeStateSchema`.
- **Handler**: `handleWhiteboardDraw` validates and creates strokes; MAX_STROKES=5000
  ring buffer. `handleWhiteboardClear` removes all strokes.
- **UI**: `WhiteboardPanel.tsx` with HTML5 Canvas (800x600), pen/eraser tools,
  8-color palette, 3 width sizes. `useWhiteboard` hook manages state.
- **Interactable**: `whiteboard` is the 10th interactable type in
  `InteractableManager`.

### Spotlight/Presentation
- **Server**: Module-level `currentPresenter` (follows megaphone pattern).
  First-come-first-served. `handleSpotlightStart/Stop`, `releaseSpotlight`
  on disconnect. `spotlightPresenter` field on `OfficeStateSchema`.
- **UI**: `SpotlightView.tsx` (80vh video panel for audience),
  `SpotlightControls.tsx` (start/stop), `useSpotlight` hook.

### In-Browser Map Editor
- **Backend**: `Map` model + migration `0008_add_maps_table`. CRUD API at
  `/api/v1/maps` (follows `workflows.py` pattern). Import/export TMJ.
- **UI**: `MapEditor.tsx` full-screen modal with `MapCanvas` (HTML5 Canvas tile
  painter, 32x32 tiles, pan/zoom, multi-layer), `TilePalette`, `ObjectPalette`,
  `MapToolbar` (New/Save/Load/Export/Import/Undo/Redo/Grid), `MapProperties`.
- **Converter**: `map-converter.ts` — `internalToTmj()`/`tmjToInternal()`
  matching `TiledMapLoader.ts` 9-layer contract.
- **Hook**: `useMapEditor` with undo/redo stack (max 50), CRUD via maps API.
- Accessed via "Map Editor" button in DashboardPanel header.

### Calendar Integration (`packages/calendar`)
- **Adapters**: `GoogleCalendarAdapter` (Calendar API v3),
  `MicrosoftCalendarAdapter` (Graph API v1.0). Both expose `list_events()`
  and `check_busy()` via `httpx.AsyncClient`.
- **DB**: `CalendarConnection` model + migration `0009_add_calendar_connections`.
- **API**: `GET /api/v1/calendar/events`, `POST /connect`, `DELETE /disconnect`,
  `GET /status`.
- **UI**: `CalendarPanel.tsx` sliding panel with event list and join-meeting
  buttons. `useCalendar` hook polls every 60s, auto-sets playerStatus to "busy".

### AI Meeting Notes
- **Graph**: `build_meeting_graph()` — `transcribe` → `summarize` →
  `extract_actions` → `save_artifact` → END. Graph type: `"meeting"`,
  timeout: 300s. Saves results via `LocalFSStorage`.
- **Template**: `meeting-notes.yaml` in `data/workflow-templates/`.
- **UI**: `MeetingNotesPanel.tsx` with summary, action items, transcript.
  `useMeetingNotes` hook dispatches meeting graph and polls for result.
  "Generate Notes" button in `RecordingControls` after recording stops.

### Music/Mood Status
- `TacticianSchema.musicStatus` (`@type("string")`, default `""`). Synced via
  Colyseus. Max 50 chars.
- `handleMusicStatus` in `handlers/status.ts` validates length.
- `MusicStatus.tsx`: text input with 6 mood presets, click-to-edit.
- Rendered below player name labels in `OfficeScene`.

### Chat Persistence
- **DB model**: `ChatMessage` in `models.py` (room_id, sender_session_id,
  sender_name, content, is_system, org_id, created_at). Migration `0010`.
- **REST API**: `apps/nexus-api/nexus_api/routers/chat.py` —
  `GET /api/v1/chat/history?room_id=&limit=&before=` (paginated, org-scoped),
  `POST /api/v1/chat/messages` (fire-and-forget from Colyseus).
- **Colyseus integration**: `handleChat()` and `addSystemMessage()` in
  `handlers/chat.ts` fire-and-forget POST to nexus-api after pushing to
  state schema.
- **Browser notifications**: `useNotifications` hook requests permission,
  shows desktop notifications for chat messages when tab is unfocused.
  Respects DND status. Detects @mentions.

### Teleport & Player List
- **Teleport handler**: `handlers/teleport.ts` — `handleTeleport(state,
  client, { targetSessionId })` moves player to target position + 40px offset.
- **PlayerList component**: sliding panel listing connected players with
  Teleport and Follow buttons per player.

### Admin Controls
- **REST API**: `apps/nexus-api/nexus_api/routers/admin.py` —
  `GET /api/v1/admin/users` (connected users from Redis),
  `POST /api/v1/admin/kick` (publish to Redis channel),
  `POST /api/v1/admin/room-config`. All require `admin` JWT role.
- **AdminPanel component**: user list with kick, MOTD config form.
- **Guest access**: Implemented via Janua `POST /api/v1/auth/guest` endpoint.
  `GuestInvite` model for invite links. `require_non_guest()` FastAPI dependency
  blocks guests from dispatch, approve/deny, workflow/map CRUD, marketplace
  publish/rate/install, calendar connect/disconnect. Colyseus `onAuth` verifies
  JWT via `jose` + JWKS, blocks guests from `approve`, `deny`,
  `megaphone_start`, `spotlight_start`. Frontend `/guest` page, `useUserPermissions`
  hook, `isGuest()` helper in `api.ts`. `TacticianSchema.isGuest` field.

### Meeting Title Badge
- `TacticianSchema.meetingTitle` (`@type("string")`, default `""`). Set by
  calendar integration via `meeting_title` Colyseus message. Max 100 chars.
- `handleMeetingTitle` in `handlers/status.ts`.

### OpenAPI Documentation
- Swagger UI at `/api/v1/docs`, OpenAPI JSON at `/api/v1/openapi.json`.

### Simplified View
- `SimplifiedView.tsx`: accessible HTML-only alternative to Phaser canvas.
  Department cards (responsive grid), agent list with status badges, approval
  queue with approve/deny buttons, inline chat. Semantic HTML + ARIA landmarks.
- View mode toggle: `viewMode: 'game' | 'simple'` in `page.tsx`, persisted to
  localStorage. Toggle button in HUD.

### MADFAM Intelligence Architecture

- **Org config** (`~/.autoswarm/org-config.yaml`): Secure, per-org configuration
  outside the repo. Defines providers, task-type model assignments, priority
  lists, embedding config, and agent templates. Template at
  `data/org-config-template.yaml`. Loaded by `load_org_config()` (cached via
  `@lru_cache`). API keys referenced by env var name, never plaintext.
- **Task-type routing**: `TaskType` enum (9 values: planning, coding, fast_coding,
  review, research, crm, support, vision, embedding). Graph nodes pass
  `task_type` to `call_llm()` → `RoutingPolicy.task_type` → router checks
  `org_config.model_assignments` → sets `policy.model_override` + selects
  provider. Falls through to default priority-list routing when no assignment
  matches.
- **Model override**: All providers (OpenAI, Anthropic, Ollama) honor
  `request.policy.model_override` in `_build_body()`, falling back to
  `self._model` when not set.
- **New providers**: SiliconFlow (`SILICONFLOW_API_KEY`, GLM-5) and Moonshot
  (`MOONSHOT_API_KEY`, Kimi K2.5) registered in `build_model_router()`.
  Org config can define additional providers dynamically.
- **Agent roster**: 13 agents across 4 departments (Engineering×6, Research×3,
  CRM×2, Support×2) with cross-functional skills. Seed script is idempotent
  (skips existing agents by name).
- **New synergy rules**: "Quality Pipeline" (coding+webapp-testing, 1.3×).
  Total: 8 default rules.
- **Configurable embeddings**: `EmbeddingProvider` accepts optional
  `provider_name`, `model`, `base_url` for org-config-driven embedding
  providers (e.g. DeepInfra Nemotron). Falls back to OpenAI
  text-embedding-3-small.

## Architecture Notes

- **Worker execution pipeline**: `process_task()` in `__main__.py` drives the
  full task lifecycle: (1) set status to `"running"` via `task_status.py`, (2)
  execute the LangGraph graph, (3) map graph status → API status
  (`pushed`/`completed` → `"completed"`, `blocked`/`denied`/`error` → `"failed"`)
  and PATCH to `nexus-api`, (4) publish agent status to Colyseus via Redis
  pub/sub. Timeouts and exceptions also PATCH `"failed"` with error details.
  All status updates are fire-and-forget (failures logged, never raised).
- **Coding graph execution**: `plan()` creates a git worktree and sets
  `branch_name: "autoswarm/task-{id}"`. `implement()` calls the LLM requesting
  JSON `{"files": [...]}`, parses the response, and writes files to the worktree
  via `_write_files_to_worktree()` (with path traversal security checks). Falls
  back to a placeholder file when no LLM is configured. `push_gate()` calls
  `git_tool.commit()` + `git_tool.push()` before worktree cleanup on approval.
- **Permission engine wiring**: `check_permission()` in `base.py` evaluates an
  `ActionCategory` against the `PermissionEngine`. Called by `implement()`
  (`file_write`), CRM `send()` (`email_send`), and deployment `validate()`
  (`deploy`). Returns `DENY` → node returns `status: "blocked"`. The
  `push_gate` and `deploy_gate` use `interrupt()` for ASK-level gating.
  Skill-based overrides apply when `agent_skill_ids` are present.
- **GitHub credential handling**: `GitTool.configure_credentials()` sets a
  repo-local `credential.helper` echoing the token. `push()` accepts an
  optional `token` kwarg and calls `configure_credentials()` automatically.
  `push_gate()` reads `settings.github_token` and passes it through.
- **PR creation after push**: `_create_pr_after_push()` in `coding.py` calls
  `GitTool.create_pr()` (which invokes `gh pr create`) after a successful push.
  Fire-and-forget — failures are logged, never raised.
- **Deployment graph**: `apps/workers/autoswarm_workers/graphs/deployment.py`
  implements `validate → deploy_gate (interrupt) → deploy → monitor → END`.
  Uses `DeployTool` and `DeployStatusTool` from `packages/tools`.
- **Enclii webhook**: `POST /api/v1/gateway/enclii` receives deployment events
  from Enclii. Bearer token auth via `enclii_webhook_secret`. Maps
  `deploy_failed`/`deploy_rollback` → `coding`, `deploy_succeeded` → `research`.
  Creates SwarmTasks and enqueues to Redis.
- **Task queue**: Redis Streams (`autoswarm:task-stream`) with consumer groups
  (`autoswarm-workers`).
  Dead letter queue at `autoswarm:task-dlq` after 3 retries. Workers auto-claim
  stalled messages on startup via XAUTOCLAIM.
- **Redis pool**: `packages/redis-pool/` provides a singleton `RedisPool` with circuit
  breaker and exponential backoff. All Python services use `get_redis_pool()` instead
  of one-off `aioredis.from_url()` calls. Colyseus uses `redis-client.ts` singleton.
- **Observability**: `packages/observability/` provides shared `configure_logging()`,
  `bind_task_context()`, `init_sentry()` for Python. TypeScript uses pino via
  `packages/config/logging.ts`. All services emit structured JSON logs with
  `request_id` correlation. Prometheus metrics on `/metrics` endpoints.
- **Health endpoints**: nexus-api (`/api/v1/health/*`), gateway (`:4304/health`),
  workers (`:4305/health`), colyseus (`:4303/health`). Queue stats at
  `/api/v1/health/queue-stats`.
- WebSocket approval events use the `ConnectionManager` singleton in
  `apps/nexus-api/src/ws.py`.
- LangGraph `interrupt()` is used to pause agent execution for HITL approval.
- Synergy bonuses stack multiplicatively (see `packages/orchestrator/src/synergy.py`).
  Synergy rules support both role-based (`required_roles`) and skill-based
  (`required_skills`) requirements.
- `SwarmOrchestrator.match_agents_by_skills()` selects idle agents by skill overlap
  score. The swarms router auto-selects agents when `required_skills` is provided
  without explicit `assigned_agent_ids`.
- Agents have `skill_ids` (JSON column) and `effective_skills` (computed from
  `skill_ids` or `DEFAULT_ROLE_SKILLS` fallback). Skills flow from DB → API →
  Colyseus schema → Phaser UI badges.
- The gateway `HeartbeatService` (cron-based, `apps/gateway/`) scrapes GitHub
  events and dispatches enemy waves via WebSocket to the approvals endpoint,
  which converts them into `SwarmTask` records enqueued on Redis.
- **GitHub webhook endpoint**: `POST /api/v1/gateway/github` receives push-based
  webhooks from GitHub (PR opened/synced, issues opened, CI failures). Verifies
  `x-hub-signature-256` via `GITHUB_WEBHOOK_SECRET` env var. Maps events to
  SwarmTasks and enqueues on Redis.
- **Agent movement**: `AgentBehavior` (`apps/office-ui/src/game/AgentBehavior.ts`)
  drives agent patrol within department zones (idle), walk-to-review-station
  (waiting_approval), and freeze (working/error). 30px/s patrol, 60px/s to station.
- **Auth flow**: Next.js middleware checks `janua-session` cookie. Login page
  supports both dev bypass (dummy JWT) and Janua SSO redirect (when
  `NEXT_PUBLIC_JANUA_ISSUER_URL` is set). `apiFetch()` in `src/lib/api.ts`
  attaches Bearer token from cookie to all API calls.
- **Security middleware** (`nexus_api/middleware/security.py`): Adds CSP header
  (configurable via `csp_extra_sources` setting), `Permissions-Policy` allowing
  camera/mic for own origin (WebRTC), and standard security headers. CSP
  `connect-src` auto-includes CORS origins and `ws:/wss:`.
- **CSRF middleware** (`nexus_api/middleware/csrf.py`): double-submit cookie
  pattern. Bearer-authenticated requests skip CSRF validation (Bearer tokens
  are inherently CSRF-safe). Webhook endpoints (`/api/v1/gateway/`,
  `/api/v1/billing/webhooks/`, `/api/v1/approvals/ws`, `/api/v1/health/`) are
  also exempt.
- **WebSocket rate limiting**: `MessageRateLimiter` in `ws.py` (30 msg/60s
  per client). Used by events and approvals WS endpoints. Colyseus uses
  `MessageThrottler` (30 msg/sec, exempt: `move`, `webrtc_signal`).
- **Fire-and-forget retry**: `http_retry.py` provides `fire_and_forget_request()`
  with exponential backoff (0.5s→1s→2s) and per-host circuit breaker (5
  failures→30s cooldown). Used by `task_status.py` and `event_emitter.py`.
- **Database pool**: Configurable via `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`,
  `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT` env vars. Pool stats at
  `/api/v1/health/pool-stats`.
- **Env validation**: `@model_validator` on both nexus-api and worker `Settings`.
  Validates URL formats, warns on insecure defaults in non-dev environments.
- **OpenTelemetry**: Optional tracing via `OTEL_EXPORTER_OTLP_ENDPOINT` env var.
  No-op when unset. W3C Trace Context propagation. Redis pool OTel spans.
- **Colyseus auth**: `onAuth` verifies JWT via `jose` + Janua JWKS.
  `filterBy(["orgId"])` for room-per-org isolation. Dev bypass preserved.
- **Playwright E2E**: `tests/e2e/` with login, dispatch, and approval specs.
  Run with `make test-e2e` (requires `npx playwright install chromium`).
- Worker graph nodes (`plan`, `implement`, `review`) use `call_llm()` from
  `autoswarm_workers.inference` with a `ModelRouter` that auto-discovers providers
  from env vars. Graphs fall back to static logic when no LLM is configured.
- The permission matrix is evaluated by `packages/permissions/src/engine.py` before
  every tool invocation in the worker.
- **Colyseus tsconfig**: `apps/colyseus/tsconfig.json` MUST have
  `"useDefineForClassFields": false` alongside `"experimentalDecorators": true`.
  Without this, ES2022+ class field semantics override `@type` decorator
  getter/setters, causing `encodeAll()` to emit 0 bytes and clients to receive
  empty state. This is a hard requirement for `@colyseus/schema` decorators.
- **WebSocket payload**: `WebSocketTransport` is configured with
  `maxPayload: 1024 * 1024` (1 MB) because the default ws limit is too small
  when state includes 12+ agents.
- **GameEventBus caching**: `PhaserGame.tsx`'s `GameEventBus` caches the last
  emitted value per event key and replays it to late subscribers. This fixes a
  timing race where Colyseus state arrives before the Phaser `OfficeScene` is
  created.
- **Slug-based department matching**: `OfficeRoom.fetchAgentsFromApi()` matches
  API departments (which use UUID IDs) to Colyseus departments (which use
  hardcoded string IDs like `dept-engineering`) by slug. It first fetches the
  department list, then fetches detail by API UUID for each slug match.

### Multi-Player & Chat

- The Colyseus `OfficeStateSchema` uses `players: MapSchema<TacticianSchema>`
  (keyed by `client.sessionId`) instead of a single tactician. Each player has
  `sessionId`, `name`, `x`, `y`, `direction`.
- `OfficeRoom.onJoin()` creates a player entry; `onLeave()` removes it. System
  messages are broadcast to `chatMessages` on join/leave/approval events.
- `handleMovement` looks up the moving player via `state.players.get(client.sessionId)`
  so multiple players move independently.
- `chatMessages: ArraySchema<ChatMessageSchema>` holds the last 50 messages
  (user + system). The `chat` message handler validates content length (max 500).
- Office world bounds are 1600x896 (50x28 tiles at 32px).
- `OfficeScene` renders remote players as interpolated sprites with name labels.
  Local player movement is broadcast via `GameEventBus` at ~15fps with a 1px
  dead-zone to avoid flooding.
- `ChatPanel` is a collapsible React overlay (bottom-left). `T`/`/` to focus,
  `Esc` to unfocus. `GamepadManager.chatFocused` suppresses keyboard game input
  while typing.

### Tiled Map Support

- `BootScene` loads `office-default.tmj` (Tiled JSON) and an `office-tiles` image.
  `OfficeScene.create()` calls `loadTiledMap()`; on failure it falls back to the
  procedural floor + department-zone rendering that existed before.
- `TiledMapLoader.ts` parses department zones, review stations, and spawn points
  from Tiled object layers. Collision is set on an invisible `collision` layer via
  `setCollisionByExclusion([-1])`.
- The default map lives at `apps/office-ui/public/assets/maps/office-default.tmj`.

### Emotes & Reactions

- Emotes are **ephemeral** — not persisted in the Colyseus schema. The client sends
  an `emote` message with `{ type }` (one of 9 whitelisted types in
  `apps/colyseus/src/handlers/emotes.ts`). The server validates and broadcasts
  `player_emote` to all clients.
- The client renders a speech-bubble sprite above the player with a 3-second
  scale-up + fade-out tween (`OfficeScene.showEmoteBubble()`). Falls back to
  Unicode emoji text if the emotes spritesheet fails to load.
- `EmotePicker.tsx` provides a 3x3 grid UI toggled with `R`, quick-select `1-9`.
- `GamepadManager.emotePickerFocused` suppresses keyboard movement while the
  picker is open.

### Avatar Customization

- `AvatarConfig` (in `packages/shared-types/src/avatar.ts`) defines 5 properties:
  `skinTone`, `hairStyle`, `hairColor`, `outfitColor`, `accessory`.
- Config is persisted in `localStorage` via `useAvatarConfig` hook, and sent to
  the server via `avatar` message → stored as JSON string on
  `TacticianSchema.avatarConfig`.
- `AvatarCompositor.ts` generates a composite 32x32 canvas texture at runtime,
  keyed by config hash for caching. No pre-generated avatar spritesheets needed.
- `AvatarEditor.tsx` is a full-screen modal shown on first visit. Users can
  re-open it via the "Avatar" button in the top-right.
- Remote players' avatar textures are applied during `reconcileRemotePlayers()`
  based on their `avatarConfig` schema field.

### Proximity Video/Audio (WebRTC)

- **Server-side**: `proximity.ts` runs a 5Hz loop calculating which players are
  within 200px. It sends `proximity_players` messages to each client listing
  nearby session IDs. `signaling.ts` relays `webrtc_signal` messages between
  clients (SDP offers/answers, ICE candidates) — pure pass-through.
- **Client-side**: `useProximityVideo` hook manages peer connections using
  `simple-peer` (25KB). On receiving `proximity_players`, the client with the
  lexicographically lower sessionId initiates offers (deterministic, no races).
  Max 6 peers per group.
- **UI**: `VideoOverlay.tsx` renders 64px circular `<video>` bubbles (React DOM
  over Phaser canvas). `MediaControls.tsx` provides M (mute) and V (camera)
  toggle buttons.
- **STUN**: Google free STUN servers for dev. Add coturn for production.
- **Dependency**: `simple-peer@^9.11.1`, `@types/simple-peer@^9.11.8`.

### Interactive Map Objects

- `InteractableManager` (`apps/office-ui/src/game/InteractableManager.ts`) parses
  the `interactables` Tiled object layer and creates Phaser zones with overlap
  detection. Each object has an `interactType` property: `url`, `popup`,
  `jitsi-zone`, `silent-zone`, `dispatch`, `blueprint`, `desk`,
  `restricted-zone`, or `room-transition`.
- When the player overlaps an interactable zone, a `[E] label` prompt appears.
  Pressing E (buttonX) triggers the action.
- `url` and `jitsi-zone` types emit `open_cowebsite` → `CoWebsitePanel.tsx`
  renders a sliding iframe panel from the right (50vw max 640px, sandboxed).
- `popup` type emits `show_popup` → `PopupOverlay.tsx` renders a centered modal.
- `silent-zone` emits `silent_zone_enter`/`silent_zone_exit` events for
  muting proximity audio (Feature 4).
- `dispatch` type emits `open_dispatch` → `TaskDispatchPanel.tsx` renders a
  sliding form panel for dispatching swarm tasks.

### Mobile Support

- `VirtualJoystick` (`apps/office-ui/src/game/VirtualJoystick.ts`) renders at
  bottom-left: 80px base + 32px thumb, pointer drag with 0.2 deadzone.
  Only responds to left-half screen touches.
- `TouchActionButtons` (`apps/office-ui/src/game/TouchActionButtons.ts`) renders
  4 circular buttons at bottom-right: Approve (green), Deny (red), Inspect (cyan),
  Emote (yellow).
- `useTouchDetection` hook detects touch capability and orientation.
- OfficeScene applies 1.5x camera zoom on touch devices for better visibility.
- Joystick input merges with gamepad/keyboard in the update loop.

### Task Dispatch UI

- `useTaskDispatch` hook (`apps/office-ui/src/hooks/useTaskDispatch.ts`) POSTs to
  `POST /api/v1/swarms/dispatch`. State machine: idle → submitting → success | error.
- `TaskDispatchPanel` (`apps/office-ui/src/components/TaskDispatchPanel.tsx`) is a
  sliding panel (right side, w-80) with description, graph type selector, optional
  agent assignment, and optional skill requirements.
- Entry points: (1) walk to a dispatch station on the map → press E, (2) click
  "+ New Task" button in the DashboardPanel header.
- Dispatch stations are `interactables` objects in `office-default.tmj` with
  `interactType: "dispatch"` at (304,296) and (544,296) in the central corridor.
- Mutual exclusion: opening dispatch panel closes the dashboard panel.
- Uses `chat-focus` gameEventBus event to suppress keyboard game input while typing.

### Map Scripting API (Feature 9)

- `ScriptBridge` (`apps/office-ui/src/game/scripting/ScriptBridge.ts`) manages
  hidden sandboxed iframes for map scripts. Scripts defined via `scriptUrl`
  property on the Tiled map. Communication via `postMessage` with command whitelist.
- `ScriptAPI` (`apps/office-ui/src/game/scripting/ScriptAPI.ts`) defines the
  `AS.*` namespace injected into script iframes: `AS.chat.sendMessage()`,
  `AS.camera.moveTo()`, `AS.player.moveTo()`, `AS.ui.openPopup()`,
  `AS.ui.openCoWebsite()`, `AS.onPlayerEntersArea()`, `AS.onPlayerLeavesArea()`.
- `InteractableManager` emits `zone_enter`/`zone_leave` events on the gameEventBus;
  `OfficeScene` forwards these to `ScriptBridge.notifyAreaEvent()`.
- Lifecycle: created on map load if `scriptUrl` property exists, destroyed on
  scene shutdown.

### Click-to-Move & Pathfinding

- `Pathfinder` (`apps/office-ui/src/game/Pathfinder.ts`): A* pathfinding on
  the Tiled collision grid. Manhattan heuristic, 4-directional, 2000 iteration
  safety cap. Falls back to direct line when no collision layer.
- `pointerup` handler in `OfficeScene.createTactician()` computes path on left
  click, spawns fading indigo marker at destination.
- Click path followed in `update()` via normalized direction injection into
  `stickX`/`stickY`. Keyboard/gamepad input immediately cancels click path.
- `GamepadManager.isFocused()` suppresses clicks while chat/emote picker open.

### Follow Player Camera

- `F` key follows nearest remote player. Camera switches to track their sprite.
- ESC or manual movement cancels follow.
- `followLabel` text overlay shows "Following: [name]" while active.
- `follow-status` gameEventBus event updates HUD badge in React.

### Explorer Mode

- `Tab` toggles explorer mode: zooms camera out to show full map, enables
  scroll-to-pan with movement sticks, disables player movement.
- `Tab` or `ESC` exits explorer mode, restoring previous zoom + camera follow.
- `explorer-mode` gameEventBus event updates HUD badge in React.
- Agent behavior continues running during explorer mode.

### Player Status (Away/Busy/DND)

- `TacticianSchema.playerStatus` (`@type("string")`, default `"online"`):
  synced via Colyseus to all clients. Values: `online`, `away`, `busy`, `dnd`.
- `handleStatus` (`apps/colyseus/src/handlers/status.ts`): validates against
  whitelist, follows `emotes.ts` handler pattern.
- `usePlayerStatus` hook: 5-min auto-away timer (30s check interval),
  auto-restore on activity (mousemove/keydown/pointerdown).
- `StatusSelector` component: dropdown with colored dots (green/amber/red/grey).
- Status dot rendered next to remote player name labels in `OfficeScene`.
- DND status suppresses proximity video connections in `useProximityVideo`.

### Personal Desks

- `desk` interactable type in `InteractableManager` with `assignedAgentId`
  property parsed from Tiled objects.
- `AgentBehavior.setDeskPosition()` overrides agent home position so idle
  agents patrol around their assigned desk.
- Desk positions wired in `OfficeScene.onStateUpdate()` after agent reconciliation.
- `DeskInfoPanel` component shows agent name, role, status, and skills on
  desk interaction. Emits via `open_desk_info` gameEventBus event.

### Screen Sharing

- `toggleScreenShare()` in `useProximityVideo`: uses `getDisplayMedia()` to
  capture screen, replaces video track on all active peers via
  `RTCRtpSender.replaceTrack()`. Auto-stops on `track.onended` (browser UI).
- Screen share button (S key) in `MediaControls.tsx`.
- Local video preview shows "Screen" label at 128px when sharing.

### Local Recording

- `useRecording` hook (`apps/office-ui/src/hooks/useRecording.ts`): mixes local
  + remote audio via `AudioContext.createMediaStreamDestination()`, records with
  `MediaRecorder` (webm/vp9+opus). Downloads on stop. Browser-local only.
- `RecordingControls` component: red pulsing record button with duration timer.
- States: `idle` | `recording` | `processing`.

### Locked Bubbles

- Server-side locked groups in `proximity.ts`: `lockBubble()` captures current
  nearby players into a locked set. Locked members only see each other in
  proximity calculations. Outsiders cannot join locked groups.
- `lock_bubble`/`unlock_bubble` Colyseus messages. Any member can unlock.
- `removeFromLockedGroups()` called on player leave. Groups dissolve when < 2.
- Lock button (L key) in `MediaControls.tsx` with amber highlight when active.

### Area Access Restrictions

- `restricted-zone` interactable type with `requiredTags` property (comma-separated).
- `InteractableManager.setPlayerTags()` sets the player's tags for access checks.
- Players without required tags are pushed out of restricted zones.
- `access_denied` gameEventBus event emitted once per zone entry attempt.

### Companions/Pets

- `TacticianSchema.companionType` (`@type("string")`, default `""`): synced
  via Colyseus. Values: `""`, `cat`, `dog`, `robot`, `dragon`, `parrot`.
- `handleCompanion` handler validates against whitelist (follows emotes pattern).
- `CompanionBehavior` class follows owner with lag (speed 180, follow distance
  28px, lerp factor 0.08). Rendered as 8x8 colored rectangles in OfficeScene.
- `reconcileCompanionSprite()` in OfficeScene creates/updates/removes companions
  during remote player reconciliation.
- Companion selection tab in `AvatarEditor.tsx`. Persisted to localStorage.
- Companion sprite data in `packages/shared-types/src/sprite-data/companions.json`.

### Megaphone/Broadcast

- One speaker at a time (first-come-first-served). Module-level state in
  `handlers/megaphone.ts`.
- `megaphone_start`/`megaphone_stop` messages. `releaseMegaphone()` on disconnect.
- Speaker's sessionId injected into ALL players' nearbySessionIds in
  `startProximityLoop()`, enabling room-wide audio.
- `MegaphoneControls.tsx` component with pulsing broadcast indicator.

### Multi-Room Navigation

- `room-transition` interactable type in InteractableManager. `content` field
  specifies target room ID.
- `room_transition` gameEventBus event updates URL `?map=` parameter.
- `RoomNavigator.tsx` dropdown component (bottom-right) with 4 predefined rooms.
- Room switching reloads the Tiled map via `?map=<name>` URL parameter.

### Noise Suppression

- `audio-processor.ts` utility: WebAudio filter chain with highpass(80Hz) +
  DynamicsCompressor. Returns processed output stream.
- `toggleNoiseSuppression()` in useProximityVideo: lazy-imports the audio
  processor, replaces audio track on all peers via `replaceTrack()`.
- Toggle button (N key) in MediaControls with emerald highlight when active.

### UI/UX Infrastructure

- **ErrorBoundary** (`apps/office-ui/src/components/ErrorBoundary.tsx`) wraps the
  main page content. Class component with fallback UI + retry button.
- **Toast system**: `ToastProvider` wraps the app in `page.tsx`. Use
  `useToast().addToast(message, severity)` from any component. Toasts auto-dismiss
  after 5s with a 200ms exit animation (`animate-slide-out-right`). Toasts have a
  `dismissing` flag for exit animation state. Severity: `success`, `error`,
  `warning`, `info`.
- **Focus trapping**: `useFocusTrap(active)` hook returns a ref. Applied to
  `AvatarEditor`, `PopupOverlay`, `TaskDispatchPanel`. Traps Tab cycling and
  restores previous focus on close.
- **Loading screen**: `BootScene.preload()` renders a progress bar with percentage
  during asset loading. Loading text pulses (alpha 0.7→1). Rotating tips cycle
  below the bar every 2.5s ("Walk near agents to interact...", etc.).
- **Help overlay**: Press `?` to toggle. Has backdrop, `[X]` close button, and
  gamepad mappings alongside keyboard shortcuts.
- **Design system tokens** in `tailwind.config.ts`:
  - Semantic colors: `semantic-success`, `semantic-error`, `semantic-warning`,
    `semantic-info`
  - Z-index scale: `z-hud` (20), `z-video` (30), `z-backdrop` (40),
    `z-modal` (50), `z-toast` (60)
  - Typography: `text-retro-xs` (7px), `text-retro-sm` (8px),
    `text-retro-base` (10px), `text-retro-lg` (12px)
  - Button `xs` size variant in `packages/ui/src/button.tsx`
- **Font loading**: Press Start 2P loaded via `next/font/google` in `layout.tsx`
  (CSS variable `--font-pixel`). No HTTP `@import` in globals.css.
- **iframe sandbox**: `CoWebsitePanel` uses `allow-scripts allow-forms allow-popups`
  (no `allow-same-origin`).
- **Global focus indicators**: `*:focus-visible` outline set in `globals.css`.
- **Responsive panels**: `ChatPanel`, `DashboardPanel`, `TaskDispatchPanel` use
  `w-full max-w-80 sm:w-80` for mobile.
- **Responsive game fonts**: `responsiveFontSize(base)` in `OfficeScene.ts` scales
  with viewport width.
- **Touch feedback**: VirtualJoystick thumb alpha (0.4 idle/0.9 active),
  TouchActionButtons scale+alpha on press, 48px min touch targets.
- **CSS animation vocabulary** in `globals.css` (`@layer utilities`):
  - `animate-slide-in-right` / `animate-slide-out-right` (300ms/200ms)
  - `animate-fade-in` / `animate-fade-in-up` (200ms/250ms)
  - `animate-pop-in` with spring overshoot (300ms cubic-bezier)
  - `animate-pulse-border` for glowing borders (2s infinite)
- **`.retro-btn` class** in `globals.css`: hover=translateY(-1px)+glow,
  active=translateY(1px)+inset shadow. Applied to dashboard toggle, avatar
  button, chat toggle, emote button, and avatar editor action buttons.
- **`.retro-panel:hover` glow**: subtle indigo box-shadow expansion on hover.
- **CRT scanline overlay**: `.scanline-overlay::after` in `globals.css` with
  `repeating-linear-gradient` at 3% opacity. Applied to `<main>` in `page.tsx`.
- **Phaser post-FX**: CRT vignette on main camera, gated behind
  `ENABLE_POST_FX` constant in `OfficeScene.ts`.
- **Particle system**: Ambient dust motes (1 per 800ms, ADD blend, alpha
  0→0.3), tactician walk dust trail, agent status particles (cyan sparkles
  for working, red wisps for error). All gated behind `ENABLE_PARTICLES`.
  Runtime-generated 2x2 (`particle-dot`) and 3x3 (`particle-dust`) textures
  in `BootScene.ts`.
- **Department zone ambient pulse**: alpha-breathing tween (0.2→0.35) on zone
  overlays, staggered by index.
- **Agent status halos**: colored circle beneath each agent (slate=idle,
  cyan=working, amber+pulse=waiting_approval, red=error). Stored in
  `AgentSprite.statusHalo`.
- **Agent idle breathing**: subtle scaleY tween (1.0→1.04, 2s) on idle agents.
  Paused when status changes away from idle.
- **Agent name label backgrounds**: black rectangle at 0.5 alpha behind name
  text for readability over zone colors. Both `nameLabel` and `nameBackground`
  are stored in `AgentSprite` and repositioned each frame alongside the sprite.
- **Review station glow**: pulsing alpha tween + `preFX.addGlow()` when
  `pendingApprovals > 0`. Cleared when 0.
- **Tactician spawn-in effect**: scale 0.5→1.0 + alpha 0→1 with Back.easeOut,
  indigo particle burst (8 particles).
- **Chat bubbles**: local messages right-aligned (`bg-indigo-900/50`), remote
  left-aligned (`bg-slate-800/60`), system centered italic. Staggered
  `animate-fade-in-up`.
- **Dashboard enhancements**: backdrop overlay when open (click-to-close),
  kanban cards with left-border color by status + hover translate, department
  stat bars (cyan agents bar, amber tasks bar), staggered fade-in.
- **HUD count animation**: agent count and approval count wrapped in
  `<span key={count}>` with `animate-pop-in` (re-mounts on value change).
  Approval badge gets `animate-pulse` + `animate-pulse-border` when count > 0.
- **Functional minimap**: `Minimap` sub-component in `HUD.tsx` renders to
  128x96 `<canvas>`. Draws department zones as colored rectangles, agents as
  2px status-colored dots (idle=slate, working=cyan, waiting_approval=amber,
  error=red), player as 3px indigo dot with glow ring. Fed by `playerPosition`
  state from `page.tsx` (updated on `handlePlayerMove`).
- **Avatar editor canvas preview**: real 32x32 composited avatar drawn at 4x
  scale (128x128) using pure-canvas `drawAvatar()` utility extracted from
  `AvatarCompositor.ts` logic. Updates on every config change.
  `imageSmoothingEnabled = false` + CSS `image-rendering: pixelated`.
  Modal uses `retro-panel pixel-border-accent` with `animate-pop-in`.
- **Color swatch feedback**: `active:scale-90`, selected swatches get
  `ring-2 ring-indigo-400 ring-offset-2 ring-offset-slate-900`.
- **EmotePicker pop-in**: outer container `animate-pop-in`, each button
  staggered `animate-fade-in-up` (30ms), `hover:scale-110 active:scale-95`.
- **Video overlay animations**: peer bubbles `animate-pop-in` on connect.

## Sprite Assets

- Pre-generated pixel-art PNGs live in `apps/office-ui/public/assets/` (sprites,
  tilesets, UI icons). These are committed to the repo.
- Regenerate with `make generate-assets` (runs `scripts/generate-assets.js` using
  `@napi-rs/canvas`).
- **Pixel-data template system**: All sprite art is defined as 2D arrays of
  single-character palette tokens (body, hair, accessories) or direct hex colors
  (emotes, tiles, icons) in `packages/shared-types/src/sprite-data/*.json`.
  - `body.json` — 12 body templates (4 directions x 3 walk frames, 32x32)
  - `hair.json` — 16 hair overlays (4 styles x 4 directions)
  - `accessories.json` — 10 accessories (4 player + 6 agent role)
  - `emotes.json` — 9 pictographic emotes (32x32)
  - `tiles.json` — 8 tiles (32x32), `icons.json` — 4 icons (16x16)
  - `palette.json` — token definitions, `resolve-colors.ts` — avatar config to
    color map resolver with `darken()`/`lighten()` utilities
- **Shared renderers** (`renderPixelData()` + `composeLayers()`):
  - `scripts/sprite-data/renderer.js` — Node.js build-time (used by generate-assets)
  - `apps/office-ui/src/game/sprite-data/renderer.ts` — browser/Phaser runtime
- `AvatarCompositor.ts` and `AvatarEditor.tsx` both use the shared renderer +
  `resolveColorMap()` to composite body + hair + accessory layers. No duplicated
  drawing logic.
- `BootScene.ts` loads sprite files with automatic canvas-rectangle fallback if any
  PNG fails to load. Department zone overlays are always canvas-generated. The emote
  spritesheet (`emotes.png`, 9 frames at 32x32) is also loaded here. Particle
  textures (`particle-dot` 2x2, `particle-dust` 3x3) are runtime-generated.
- `OfficeScene.ts` plays walk animations for the Tactician (4 dirs x 3 frames) and
  idle/working animations for agents. Post-FX, particles, and ambient effects are
  gated behind `ENABLE_POST_FX` and `ENABLE_PARTICLES` constants.

### Palette Presets & Color Utilities

- **Palette presets** (`packages/shared-types/src/sprite-data/palette-presets.ts`):
  10 named presets (default, cyberpunk, forest, desert, arctic, ocean, volcano,
  neon, monochrome, pastel). Each defines environment colors (floor, wall, dept
  zones, review station), optional `avatarTint`, and optional `outfitOverrides`.
- **Color utilities** in `resolve-colors.ts`: `darken()`, `lighten()`,
  `saturate()`, `hueShift()`, `tint()` — all pure hex-in/hex-out.
- `resolveEnvironmentColorMap(presetName)` returns environment colors for a preset.
- `resolveThemeColorMap(presetName, avatarConfig)` applies the preset's avatarTint
  over standard avatar colors (15% tint factor, 7.5% on skin).
- All presets tested for minimum contrast ratios (review station vs floor >= 3:1,
  wall vs floor >= 1.2:1).

### Sprite Variant Generator

- `scripts/generate-variants.js` — generates themed sprite sheets per
  role × palette preset. CLI: `--presets`, `--roles`, `--output`.
- `scripts/generate-tile-variants.js` — generates themed tilesets per preset.
- `scripts/sprite-data/variation-combiner.js` — shared layer composition logic
  with tint support for variant generation.
- `scripts/post-process-assets.sh` — optional ImageMagick 2x/4x upscale + WebP.
  Gracefully skips if ImageMagick not installed.
- `generate-assets.js` extended with `--variants` (all presets) and
  `--preset <name>` (single themed tileset) flags. Tileset is now 512x128
  (16 columns x 4 rows = 54 tiles) using both hex colors and palette tokens.
- `scripts/sprite-data/tile-definitions.js` generates 46 new tiles
  programmatically (walls, floors, furniture, stations, decorations) using
  palette tokens (FL, WL, WH, FN, etc.) for theme-ability.
- `scripts/generate-office-map.js` constructs the hand-crafted 50x28
  office-default.tmj with 9 layers (floor, walls, furniture, decorations,
  collision, departments, review-stations, interactables, spawn-points).
- Output: `apps/office-ui/public/assets/sprites/variants/<preset>/` and
  `apps/office-ui/public/assets/tilesets/variants/`.

### WFC Procedural Map Generation

- **Package**: `packages/map-gen/` (`@autoswarm/map-gen`)
  - `src/wfc.ts` — core WFC with `WFCGrid.run()`, `observe()`, `collapse()`,
    `propagate()`, backtracking retries, seeded PRNG (`createRng()`).
  - `src/rules.ts` — adjacency rules for office meta-tiles (wall, corridor,
    dept_N, dept_wall_N). `metaTileToTileId()` maps to tileset indices.
  - `src/constraints.ts` — department region detection, object placement
    (review stations, dispatch stations, spawn points), map validation.
  - `src/tmj-writer.ts` — outputs valid `.tmj` matching `TiledMapLoader.ts`
    layer contract: floor, departments, review-stations, interactables,
    spawn-points.
- **CLI**: `scripts/generate-map.js` — `--seed`, `--departments`, `--width`,
  `--height`, `--output`. Default: 40x22, 4 depts, seed 42.
- **Hand-crafted map**: `scripts/generate-office-map.js` — `--output`. Generates
  50x28 map with 4 dept rooms, corridors, lobby, blueprint nook, furniture
  clusters, collision layer. Default: `office-default.tmj`.
- **BootScene integration**: `?map=<name>` URL parameter loads
  `/assets/maps/<name>.tmj`. Default: `office-default`.
- Existing `loadTiledMap()` fallback handles any schema issues with generated maps.

### Pixelact UI Components

- **Scoped namespace**: `.pixelact` class in `globals.css` defines CSS variables
  (`--pixelact-bg`, `--pixelact-fg`, etc.) and `.pxa-btn`/`.pxa-input` styles
  with 3D pixel press effects. Avoids collision with `.retro-btn`/`.pixel-border`.
- **Pixelact colors** in `tailwind.config.ts`: `pixelact-bg`, `pixelact-fg`,
  `pixelact-border`, `pixelact-primary`, etc. Map to CSS variables.
- **Pixelact shadows**: `shadow-pixelact-raised` (3D raised) and
  `shadow-pixelact-pressed` (inset pressed).
- **PixelButton** (`packages/ui/src/pixelact/pixel-button.tsx`): CVA variants
  (default/secondary/destructive/success/ghost) × sizes (default/sm/lg).
- **PixelInput** (`packages/ui/src/pixelact/pixel-input.tsx`): styled input with
  inset shadow and focus border.
- **shadcn config**: `packages/ui/components.json` configures shadcn with
  Pixelact registry URL for future `npx shadcn@latest add` usage.
- Exported from `packages/ui/src/index.ts`.
- **Preview tool**: `scripts/preview-tileset.js` generates an HTML catalog of
  all tiles across all presets at 4x scale.

### Full-Stack Observability ("The All Seeing Eye")

- **TaskEvent model** (`models.py`): INSERT-only event record with task_id,
  agent_id, event_type, event_category, node_id, graph_type, payload,
  duration_ms, provider, model, token_count, error_message, request_id,
  org_id, created_at. Migration `0011`.
- **Event emitter** (`apps/workers/autoswarm_workers/event_emitter.py`):
  `emit_event()` — fire-and-forget POST to `/api/v1/events` + Redis PUBLISH
  to `autoswarm:events`. 2s HTTP timeout. Follows `task_status.py` pattern.
  `@instrumented_node` decorator wraps graph nodes to emit `node.entered`,
  `node.exited`, `node.error` events with `duration_ms` measurement.
- **Worker instrumentation**: All 6 graph types (coding, research, CRM,
  deployment, puppeteer, meeting) decorated with `@instrumented_node` on
  every node function. `__main__.py` emits `task.started`, `task.completed`,
  `task.failed`, `task.timeout` events. `inference.py` emits `llm.response`
  events with provider, model, token_count, duration_ms.
- **Events REST API** (`routers/events.py`): `POST /api/v1/events` (no auth,
  worker-to-API), `GET /api/v1/events` (paginated, filtered by task_id,
  agent_id, event_type, event_category, since, until),
  `GET /api/v1/events/tasks/{id}/timeline` (chronological with aggregates).
  `WS /api/v1/events/ws` (initial 50-event batch + real-time relay via
  `event_manager` ConnectionManager singleton).
- **Server-side emission**: `swarms.py` emits `task.dispatched` on dispatch,
  `approvals.py` emits `approval.approved`/`approval.denied` on decision.
  Uses `emit_event_db()` (direct DB insert, no HTTP).
- **Task board API**: `GET /api/v1/swarms/tasks/board` — DB-backed kanban
  with columns (queued/running/completed/failed), aggregated event data
  (duration_ms, total_tokens, event_count), agent name resolution.
- **Metrics API** (`routers/metrics.py`): `GET /api/v1/metrics/dashboard` —
  agent utilization %, task throughput (status counts, avg duration),
  approval latency (avg, pending), cost breakdown (by provider/model),
  error rate, trend sparklines (hourly buckets), recent errors. Period
  options: 1h, 6h, 24h, 7d, 30d.
- **OpsFeed component** (`OpsFeed.tsx`): Sliding panel (left side) with
  real-time event stream via `useEventStream` WebSocket hook. Category
  filter pills, text search, auto-scroll, color-coded event cards.
  Capped at 500 in-memory events. "Load more" pagination.
- **Enhanced DashboardPanel**: Rewritten to use `useTaskBoard` hook (DB-backed)
  instead of `deriveTasksFromAgents()` (snapshot-derived). TaskCard shows
  description, graph_type badge, agent names, duration, token count, event
  count. Click-to-expand timeline view shows chronological events.
- **MetricsDashboard component** (`MetricsDashboard.tsx`): Full-screen modal
  with period selector, stat cards (utilization, throughput, approval queue,
  error rate), SVG sparklines (zero-dependency), CSS bar chart for cost
  breakdown, task status breakdown, recent errors list.
- **Page integration**: "Ops Feed" and "Metrics" buttons in top-left HUD.
  OpsFeed opens left panel; MetricsDashboard opens full-screen modal.
- **Shared types** (`packages/shared-types/src/events.ts`): EventCategory,
  EventType, TaskEvent, TaskTimeline, TaskBoardItem, TaskBoardResponse,
  TrendPoint, MetricsDashboard TypeScript interfaces.
- **CSRF**: `/api/v1/events/` and `/api/v1/events/ws` exempt from CSRF
  middleware (worker-to-API calls don't carry cookies).
