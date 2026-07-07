# Simple Kanban

A small, deployable Kanban board for scrum/software teams — **Svelte 5 + FastAPI + PostgreSQL**.
Its defining goal is **API-first**: every UI action is a plain REST endpoint, so a future MCP
server, CLI, or LLM agent can drive the board without any UI or backend rework.

> **Status: MVP in progress — a walking skeleton (Slice 1).**
> The board currently **lists columns and creates cards**. Editing, deleting, and drag-to-move are
> planned and fully specified in [`docs/`](docs/) but not yet built. See
> [Current status](#current-status) below before assuming a feature exists.

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
| Hosting (planned) | Fly.io (app) + Neon (Postgres), CI/CD via GitHub Actions |

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

## Project layout

```
backend/     FastAPI app (app/), Alembic migrations (alembic/), pyproject.toml
frontend/    Svelte 5 SPA (src/), Vite config
docs/        Shape Up planning: FRAME → PRD/CONTEXT → SHAPING → BREADBOARD + ADRs
docker-compose.yml   Local Postgres for dev/CI parity
```

## API

REST + JSON under `/api`, with interactive OpenAPI docs at **`/docs`**. Implemented today:

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/cards` | List all cards (client groups by column, sorts by position) |
| `POST` | `/api/cards` | Create a card (appended to the end of its column) |
| `GET`  | `/api/health` | Health check |

Planned: `GET/PATCH/DELETE /api/cards/{id}` and `POST /api/cards/{id}/move` (see
[`docs/BREADBOARD.md`](docs/BREADBOARD.md) §6 for the full contract).

## Current status

This repo is built in vertical slices. Slice 1 proves the end-to-end path (DB → API → UI):

| Area | Now | Planned |
|------|-----|---------|
| View board | ✅ three columns, cards rendered in order | — |
| Create card | ✅ with ticket number, story points, assignee | — |
| Edit / delete card | ⬜ | `PATCH` / `DELETE` + UI |
| Move & reorder (drag-and-drop) | ⬜ | `/move` endpoint + `renumber_column()` + drag UI |
| Seed data | ⬜ | Alembic data migration |
| Tests, Dockerfile, CI/CD, deploy | ⬜ | `pytest` + smoke test, multi-stage image, GitHub Actions → Fly.io/Neon |

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
