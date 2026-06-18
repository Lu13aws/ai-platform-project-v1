.PHONY: help install install-dev lint format type-check check test test-unit \
        test-integration test-e2e test-fast dev-up dev-up-tools dev-down \
        dev-reset dev-logs db-shell migrate migrate-new migrate-down \
        migrate-history migrate-current run-rag-demo run-private-hub ingest clean env-check

PYTHON := uv run python
UV     := uv

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────────────

install: ## Install production dependencies only
	$(UV) sync --no-dev

install-dev: ## Install all dependencies including dev tools
	$(UV) sync

# ── Code Quality ──────────────────────────────────────────────────────────────

lint: ## Run ruff linter (check only)
	$(UV) run ruff check aiplatform/ apps/ tests/

format: ## Run ruff formatter and auto-fix lint issues
	$(UV) run ruff format aiplatform/ apps/ tests/
	$(UV) run ruff check --fix aiplatform/ apps/ tests/

type-check: ## Run mypy static type checking
	$(UV) run mypy aiplatform/ apps/

check: lint type-check ## Run all checks without modifying files

# ── Testing ───────────────────────────────────────────────────────────────────

test: ## Run all tests with coverage
	$(UV) run pytest tests/ --cov=aiplatform --cov=apps --cov-report=term-missing

test-unit: ## Run unit tests only (no Docker required)
	$(UV) run pytest tests/unit/ -v

test-integration: ## Run integration tests (requires: make dev-up + make migrate)
	$(UV) run pytest tests/integration/ -v

test-e2e: ## Run end-to-end tests (requires: make dev-up + make migrate)
	$(UV) run pytest tests/e2e/ -v

test-fast: ## Run unit tests without coverage (fastest feedback)
	$(UV) run pytest tests/unit/ -v --no-cov

# ── Local Infrastructure ──────────────────────────────────────────────────────

dev-up: ## Start local PostgreSQL (detached)
	docker compose up -d
	@docker compose exec postgres pg_isready -U aiplatform -d aiplatform

dev-up-tools: ## Start PostgreSQL + pgAdmin
	docker compose --profile tools up -d

dev-down: ## Stop containers (data preserved)
	docker compose down

dev-reset: ## Stop containers AND wipe data volume (destructive)
	docker compose down -v

dev-logs: ## Tail PostgreSQL logs
	docker compose logs -f postgres

db-shell: ## Open psql shell to local DB
	docker compose exec postgres psql -U aiplatform -d aiplatform

# ── Database Migrations ───────────────────────────────────────────────────────

migrate: ## Run all pending Alembic migrations
	$(UV) run alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new MSG="add users table")
	$(UV) run alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Roll back the last migration
	$(UV) run alembic downgrade -1

migrate-history: ## Show migration history
	$(UV) run alembic history --verbose

migrate-current: ## Show current DB schema version
	$(UV) run alembic current

# ── Applications ──────────────────────────────────────────────────────────────

run-rag-demo: ## Start the RAG Demo API server with hot reload
	$(UV) run uvicorn apps.rag_demo.main:app --reload --port 8000 --host 0.0.0.0

run-private-hub: ## Start the Private Knowledge Hub on localhost:8001 (local only)
	$(UV) run uvicorn apps.private_hub.main:app --reload --port 8001 --host 127.0.0.1

ingest: ## Ingest documents (usage: make ingest PATH=./docs/myfile.pdf)
	$(UV) run rag-demo ingest --path "$(PATH)"

# ── Utilities ─────────────────────────────────────────────────────────────────

env-check: ## Verify settings load without errors
	$(PYTHON) -c "from aiplatform.settings import settings; print('Settings OK:', settings.app_env)"

clean: ## Remove caches, build artifacts, coverage files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info"  -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ dist/ build/
