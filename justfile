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
analyze +pdfs:
    uv run python scripts/analyze.py {{pdfs}}

# Evaluate the extraction against the golden set and write eval/RESULTADOS.md
# (calls the real LLM; extra flags: --variants, --limit N, --reuse)
[working-directory('backend')]
eval *args:
    uv run python scripts/eval_extraction.py {{args}}

# Validate the golden set annotations (no LLM calls)
[working-directory('backend')]
eval-check:
    uv run python scripts/eval_extraction.py --check

# Load the demo snapshots (data/demo) into the database; safe to run again
[working-directory('backend')]
demo-seed:
    uv run python scripts/demo.py seed

# Delete documents, analyses and profiles, then load the demo snapshots again
[working-directory('backend')]
demo-reset:
    uv run python scripts/demo.py reset --yes

# Analyze the demo editais with the real LLM and write their snapshots (costs money)
[working-directory('backend')]
demo-generate:
    uv run python scripts/demo.py generate --yes

# Write one analysis of the database as data/demo/NAME.json
[working-directory('backend')]
demo-export analysis name:
    uv run python scripts/demo.py export {{analysis}} {{name}}
