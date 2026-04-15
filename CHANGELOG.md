# Changelog

All notable changes to AutoSwarm Office will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-03-15

### Added

- **Guest Access**: Dedicated `/guest` join page with invite links, JWT-based
  guest tokens (via Janua), and per-endpoint permission gating (guests can
  observe but cannot dispatch tasks, approve/deny, or edit workflows).
- **Security Headers**: Content-Security-Policy header with configurable
  `csp_extra_sources`. Fixed `Permissions-Policy` to allow WebRTC camera and
  microphone for the app's own origin.
- **WebSocket Rate Limiting**: Sliding-window rate limiter for nexus-api WS
  endpoints and per-client message throttling in Colyseus (exempt: `move`,
  `webrtc_signal`).
- **Fire-and-Forget Retry**: Shared `http_retry.py` utility with exponential
  backoff (0.5s → 1s → 2s) and per-host circuit breaker (5 failures → 30s
  cooldown). Used by `task_status.py` and `event_emitter.py`.
- **Database Pool Tuning**: Configurable `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`,
  `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT` env vars. New `/api/v1/health/pool-stats`
  endpoint.
- **Environment Variable Validation**: Pydantic `@model_validator` on both
  nexus-api and worker `Settings`. Warns on insecure defaults in non-dev
  environments, validates URL formats at startup.
- **OpenTelemetry Foundation**: Optional tracing via `OTEL_EXPORTER_OTLP_ENDPOINT`
  env var. No-op when unset. W3C Trace Context propagation in request-id
  middleware. OTel spans on Redis pool operations.
- **Playwright E2E Tests**: Foundation test suite (login, task dispatch,
  approval flow) with shared fixtures for dev-auth-bypass login.
- **Admin Dashboard Tests**: vitest + @testing-library/react test suites for
  all 8 admin pages.
- **KEDA Queue Scaling Docs**: Guide and example `ScaledObject` manifest for
  Redis Stream-based worker autoscaling.
- **CHANGELOG**: Retroactive changelog in Keep a Changelog format.

### Changed

- Colyseus `onAuth` hook verifies JWT via Janua JWKS (dev bypass preserved).
  Room isolation per `orgId` via `filterBy`.
- `useUserPermissions` hook derives UI permission flags from JWT claims.
  Components hide/disable controls for guests.
- Database engine creation moved to `@lru_cache` `get_engine()` for
  configurable pool parameters.

### Removed

- Legacy Redis LIST dual-write (`LPUSH autoswarm:tasks`). Workers consume
  exclusively from Redis Streams. See `docs/MIGRATION_LEGACY_QUEUE.md`.
- `legacy_queue_depth` field from `/api/v1/health/queue-stats`.

### Fixed

- `Permissions-Policy: camera=(), microphone=()` blocked WebRTC video/audio
  on the app's own origin.
- Fire-and-forget HTTP calls in `task_status.py` and `event_emitter.py` now
  retry on failure instead of silently dropping updates.

## [0.1.0] - 2026-03-14

### Added

- Full-stack AI agent orchestration platform with gamified virtual office.
- 13 AI agents across 4 departments (Engineering, Research, CRM, Support).
- 6 LangGraph execution graphs (coding, research, CRM, deployment, puppeteer,
  meeting) plus custom YAML workflows.
- Visual Workflow Builder (React Flow) with 8 node types and conditional edges.
- Proximity-based WebRTC video/audio with locked bubbles and noise suppression.
- Avatar customization, emotes, companions, and player status.
- Interactive Tiled map with 10 interactable types, click-to-move pathfinding,
  and multi-room navigation.
- Skill Marketplace for community skill discovery and installation.
- Python SDK with CLI (`autoswarm dispatch/agents/tasks`).
- Full-stack observability: TaskEvent stream, OpsFeed, MetricsDashboard.
- MADFAM Intelligence Architecture: org-config-driven model routing, task-type
  assignments, Thompson Sampling orchestration.
- Production infrastructure: Redis Streams task queue, connection pooling with
  circuit breaker, Prometheus metrics, Sentry integration, K8s PDB/HPA/NetworkPolicy.
- Calendar integration (Google + Microsoft), AI meeting notes, chat persistence.
- Mobile support with virtual joystick and touch action buttons.
- Simplified accessible HTML-only view alternative.
- 660+ TypeScript tests, 700+ Python tests, 160+ worker tests.
