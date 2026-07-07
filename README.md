# Simple Kanban

A small, deployable Kanban board for scrum/software teams — **Svelte 5 + FastAPI + PostgreSQL**.
Its defining goal is **API-first**: every UI action is a plain REST endpoint, so a future MCP
server, CLI, or LLM agent can drive the board without any UI or backend rework.

> **🚀 Live demo: [simple-kanban-jian.fly.dev](https://simple-kanban-jian.fly.dev)**
> (Hosted on Fly.io + Neon; the free tier scales to zero, so the first request after idle can take
> ~1s to wake — that's a cold start, not a bug.)

> **Status: core board complete and deployed.**
> Viewing, creating, editing, deleting, and drag-to-move/reorder all work end to end, backed by a
> full REST API, an automated test suite, and CI/CD to Fly.io. What's left is polish — seed data
> and an end-to-end smoke test (see [Current status](#current-status)).

## What it is

Three fixed columns (**Todo / In Progress / Done**) holding cards. Each card has a Jira-style
ticket number (`KAN-1`, `KAN-2`, …), a title, and optional description, story points
({1,2,3,5,8,13}), and assignee. There's one global board, no accounts, no auth — deliberately
simple, built to ship and demo fast.

The interesting part is *how it's shaped*: a clean `/api/*` surface with auto-generated OpenAPI
docs, so the Svelte UI is just the **first** API client rather than the only way in.

## Tech stack

| Layer | Choice |
|-------|--------|
| Frontend | Svelte 5 (runes) + Vite 8, TypeScript |
| Backend | FastAPI + synchronous SQLAlchemy 2.0, Pydantic v2 (Python 3.12, deps via `uv`) |
| Database | PostgreSQL, schema managed by Alembic (psycopg v3 driver) |
| Packaging | Single artifact — FastAPI serves the built SPA from one origin (no CORS) |
| Hosting | Fly.io (app) + Neon (Postgres), CI/CD via GitHub Actions |
| Drag & drop | `svelte-dnd-action` |

See [`docs/adr/`](docs/adr/) for the reasoning behind each of these choices.

## Quick start

Prerequisites: **Docker**, **Node 20+**, and **[uv](https://docs.astral.sh/uv/)** (Python 3.12).

```bash
# 1. Start Postgres (from the repo root)
docker compose up -d db

# 2. Backend — from backend/
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # API on http://localhost:8000, docs at /docs

# 3. Frontend — from frontend/ (new terminal)
npm ci
npm run dev                               # UI on http://localhost:5173
```

Open **http://localhost:5173**. In dev, Vite proxies `/api` to the backend on `:8000`; in
production FastAPI serves the built SPA itself, so the whole thing is one origin.

Config is a single env var, `DATABASE_URL` (defaults to the docker-compose Postgres:
`postgresql+psycopg://kanban:kanban@localhost:5432/kanban`).

### Tests

```bash
# Backend — from backend/
uv run pytest tests/unit          # pure schema-validation logic, no DB
uv run pytest tests/integration   # full API against a throwaway Postgres (needs a running Docker daemon)

# Frontend — from frontend/
npm run check                     # svelte-check type/lint pass
```

The integration suite spins up an ephemeral Postgres 17 via **testcontainers** and runs the
migrations against it, so it's fully self-contained. CI runs lint, unit, integration, and the
frontend build as independent jobs on every push and PR.

## Project layout

```
backend/     FastAPI app (app/), Alembic migrations (alembic/), tests/ (unit + integration), pyproject.toml
frontend/    Svelte 5 SPA (src/), Vite config
docs/        Shape Up planning: FRAME → PRD/CONTEXT → SHAPING → BREADBOARD + ADRs
.github/workflows/   CI (lint, unit, integration, frontend build) + deploy to Fly.io
Dockerfile           Multi-stage image — builds the SPA, then serves it from FastAPI
docker-compose.yml   Local Postgres + app for dev/CI parity
fly.toml             Fly.io deployment config
```

## API

REST + JSON under `/api`, with interactive OpenAPI docs at **`/docs`**:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/cards` | List all cards (client groups by column, sorts by position) |
| `POST` | `/api/cards` | Create a card (appended to the end of its column) |
| `GET` | `/api/cards/{id}` | Read a single card |
| `PATCH` | `/api/cards/{id}` | Edit fields (title / description / story points / assignee) |
| `DELETE` | `/api/cards/{id}` | Delete a card |
| `POST` | `/api/cards/{id}/move` | Move / reorder a card (column change + position within a column) |
| `GET` | `/api/health` | Health check |

Column and position changes go through the dedicated `/move` endpoint (not `PATCH`), so field edits
and reordering stay cleanly separated. See [`docs/BREADBOARD.md`](docs/BREADBOARD.md) §6 for the full
contract.

## Current status

This repo is built in vertical slices; the core board is now feature-complete and deployed:

| Area | Status |
|------|--------|
| View board | ✅ three columns, cards rendered in order |
| Create card | ✅ with ticket number, story points, assignee |
| Edit / delete card | ✅ `PATCH` / `DELETE` + inline edit and delete-confirm UI |
| Move & reorder (drag-and-drop) | ✅ `/move` endpoint + `renumber_column()` + `svelte-dnd-action` UI |
| Tests | ✅ `pytest` unit + integration (real Postgres via testcontainers) |
| Docker / CI/CD / deploy | ✅ Dockerfile, docker-compose, GitHub Actions → Fly.io + Neon |
| Seed data | ⬜ Alembic data migration |
| End-to-end smoke test | ⬜ Playwright |

## How this project is planned

The [`docs/`](docs/) folder isn't an afterthought — it's a full [Shape Up](https://basecamp.com/shapeup)
planning trail that drives the build, and is the source of truth for *intended* behavior:

```
REQS.md  →  FRAME.md  →  PRD.md + CONTEXT.md (+ adr/)  →  SHAPING.md  →  BREADBOARD.md  →  build in slices
 (raw ask)  (framing)     (spec + glossary + decisions)   (chosen shape)  (UI places & wiring)
```

- **[CONTEXT.md](docs/CONTEXT.md)** — canonical glossary and domain model.
- **[SHAPING.md](docs/SHAPING.md)** — three candidate shapes, a fit check, and why "Thin Slice" won.
- **[BREADBOARD.md](docs/BREADBOARD.md)** — every UI place, affordance, and API wiring.
- **[adr/](docs/adr/)** — eight accepted decisions (stack, Postgres-from-day-one, single-artifact
  serving, hosting/CI, API-first, data model, no-auth/last-write-wins, implementation details).

## Non-goals (MVP)

Authentication, billing, multiple boards, custom columns, WIP limits, comments, labels,
attachments, due dates, history/audit, real-time collaboration — and the MCP/CLI/agent clients
themselves. The API is merely *designed to be ready* for them.
