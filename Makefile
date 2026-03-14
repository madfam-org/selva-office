.PHONY: dev dev-full dev-seed worker build test lint clean docker-up docker-down db-migrate db-wait setup generate-assets generate-variants post-process generate-map db-backup db-restore db-verify-backup smoke-test worktree-cleanup

# ── Development ─────────────────────────────────────
dev:
	pnpm dev & uv run --directory apps/nexus-api uvicorn nexus_api.main:app --host 0.0.0.0 --port 4300 --reload & uv run --directory apps/workers python -m autoswarm_workers

db-wait:
	@echo "Waiting for PostgreSQL..."
	@for i in $$(seq 1 30); do \
	  if command -v pg_isready >/dev/null 2>&1; then \
	    pg_isready -h localhost -p 5432 -q 2>/dev/null && break; \
	  else \
	    python3 -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('localhost',5432)); s.close()" 2>/dev/null && break; \
	  fi; \
	  sleep 1; \
	done
	@echo "PostgreSQL is ready."

dev-full:
	@echo "Starting infrastructure..."
	docker compose -f infra/docker/docker-compose.dev.yml up -d --wait
	$(MAKE) db-wait
	@echo "Running database migrations..."
	uv run --directory apps/nexus-api alembic upgrade head
	@echo "Starting all services..."
	$(MAKE) dev

dev-seed:
	@echo "Seeding departments and agents..."
	uv run python scripts/seed-agents.py

worker:
	uv run --directory apps/workers python -m autoswarm_workers

build:
	pnpm build
	uv build

test:
	pnpm test
	uv run pytest

lint:
	pnpm lint
	uv run ruff check .
	uv run mypy .

typecheck:
	pnpm typecheck
	uv run mypy .

format:
	pnpm format
	uv run ruff format .

clean:
	pnpm clean
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

# ── Docker ──────────────────────────────────────────
docker-up:
	docker compose -f infra/docker/docker-compose.yml up -d

docker-down:
	docker compose -f infra/docker/docker-compose.yml down

docker-dev:
	docker compose -f infra/docker/docker-compose.dev.yml up -d

# ── Database ────────────────────────────────────────
db-migrate:
	uv run --directory apps/nexus-api alembic upgrade head

db-seed:
	uv run python scripts/seed-agents.py

db-backup:
	bash scripts/backup-postgres.sh

db-restore:
	bash scripts/restore-postgres.sh $(BACKUP_FILE)

db-verify-backup:
	bash scripts/verify-backup.sh $(BACKUP_FILE)

# ── Assets ─────────────────────────────────────────
generate-assets:
	node scripts/generate-assets.js

generate-variants:
	node scripts/generate-variants.js
	node scripts/generate-tile-variants.js

post-process:
	bash scripts/post-process-assets.sh

generate-map:
	node scripts/generate-map.js

generate-office-map:
	node scripts/generate-office-map.js

# ── Setup ───────────────────────────────────────────
setup:
	bash scripts/setup.sh

smoke-test:
	bash scripts/smoke-test.sh

worktree-cleanup:
	bash scripts/cleanup-worktrees.sh

install:
	pnpm install
	uv sync
