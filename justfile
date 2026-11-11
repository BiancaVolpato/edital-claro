# Task runner for Edital Claro. Run "just" to list the available recipes.
# Recipes use only single commands per line so they work in both sh and PowerShell.

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# List available recipes
default:
    @just --list

# Install backend and frontend dependencies
install: install-backend install-frontend

[working-directory('backend')]
install-backend:
    uv sync

[working-directory('frontend')]
install-frontend:
    npm ci

# Start everything (Postgres + backend + frontend) with Docker
dev:
    docker compose up --build

# Start only the backend locally, with auto-reload (no Docker needed)
[working-directory('backend')]
dev-backend:
    uv run uvicorn app.main:app --reload --port 8000

# Start only the frontend locally, with auto-reload (no Docker needed)
[working-directory('frontend')]
dev-frontend:
    npm run dev

# Apply database migrations (needs a running Postgres)
[working-directory('backend')]
migrate:
    uv run alembic upgrade head

# Run the backend test suite
[working-directory('backend')]
test:
    uv run pytest

# Lint and type-check backend and frontend
lint: lint-backend lint-frontend

[working-directory('backend')]
lint-backend:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy

[working-directory('frontend')]
lint-frontend:
    npm run lint
    npm run typecheck

# Auto-format and auto-fix the backend code
[working-directory('backend')]
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Index the Lei 14.133 into PostgreSQL (needs a running, migrated database)
[working-directory('backend')]
index-law:
    uv run python scripts/index_law.py

# Measure recall@5 of the law search and write eval/law_search/RESULTADOS.md
[working-directory('backend')]
eval-law:
    uv run python scripts/eval_law_search.py

# Analyze one edital with the real LLM, no database needed (costs money)
[working-directory('backend')]
analyze pdf:
    uv run python scripts/analyze.py "{{pdf}}"

# Run the evaluation suite against the golden set (implemented in stage 9)
eval:
    @echo "A avaliacao sera implementada na Etapa 9 (ver eval/README.md)."
