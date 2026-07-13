# Simple Kanban — developer & demo shortcuts.
#
# Wraps the commands already documented in CLAUDE.md so a newcomer or agent can
# run one target instead of a multi-step sequence. Run `make` (or `make help`)
# to list everything.
#
#   make up    → the one-command full stack: `docker compose up --build`
#                (Postgres + the combined app image serving the built SPA,
#                mirroring the single production artifact per ADR 0003).
#   make dev   → the local hot-reload loop (Postgres in Docker, backend +
#                frontend running natively with live reload).
#
# Requires Docker (v2 `docker compose`), and — for the native dev/test targets —
# `uv` (backend) and `npm` (frontend). Recipe lines use TAB indentation.

# Directories
BACKEND  := backend
FRONTEND := frontend

.DEFAULT_GOAL := help

.PHONY: help up demo down down-v clean db install migrate dev \
        test test-integration e2e lint check

help: ## Show this help (the default target)
	@awk 'BEGIN {FS = ":.*##"; printf "\nSimple Kanban — make targets\n\nUsage: make <target>\n\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 } \
		END { printf "\n" }' $(MAKEFILE_LIST)

up: ## Full stack in Docker (db + app image serving the SPA) — the one-command loop; open http://localhost:8000
	docker compose up --build

demo: up ## Alias for `up` — the one-command demo of the whole app

down: ## Stop and remove the compose containers (keeps the pgdata volume)
	docker compose down

down-v: ## DESTRUCTIVE: `down` and also delete the Postgres data volume
	docker compose down -v

clean: down-v ## DESTRUCTIVE alias for `down-v` — tear everything down incl. the DB volume

db: ## Start just Postgres in the background (for the native hot-reload dev loop)
	docker compose up -d db

install: ## Install deps: backend `uv sync` + frontend `npm ci`
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci

migrate: ## Apply DB migrations (backend `alembic upgrade head`)
	cd $(BACKEND) && uv run alembic upgrade head

dev: db migrate ## Local hot-reload loop: Postgres (Docker) + backend uvicorn --reload + Vite together; Ctrl-C stops both. Open http://localhost:5173
	@trap 'kill 0' EXIT; \
	(cd $(BACKEND) && uv run uvicorn app.main:app --reload) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

test: ## Fast backend unit tests (no DB / Docker needed)
	cd $(BACKEND) && uv run pytest tests/unit

test-integration: ## Backend integration tests vs a throwaway Postgres (needs a running Docker daemon)
	cd $(BACKEND) && uv run pytest tests/integration

e2e: ## Playwright frontend e2e smoke (run `make db` first — it needs a local Postgres)
	cd $(FRONTEND) && npm run e2e

lint: ## Lint backend (ruff) + frontend (svelte-check)
	cd $(BACKEND) && uv run ruff check .
	cd $(FRONTEND) && npm run check

check: lint ## Alias for `lint` — backend ruff + frontend svelte-check
