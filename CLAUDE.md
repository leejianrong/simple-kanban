# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first: docs describe more than is built

This repo is a **walking skeleton (Slice 1)**, not the finished MVP. The [docs/](docs/) folder
specifies the full planned product ("Shape A"), but only a thin vertical slice is implemented so
far. **Do not assume a documented feature exists in code** — check the source. Code comments mark
what is deferred (e.g. "PATCH / DELETE / move come in later slices").

| Area | Built now | Documented but NOT yet built |
|------|-----------|------------------------------|
| API | `GET /api/cards`, `POST /api/cards` (append), `GET /api/health` | `GET/PATCH/DELETE /api/cards/{id}`, `POST /api/cards/{id}/move` |
| Ordering | `next_position()` (append to end) | `renumber_column()` (transactional re-sequence on move/reorder) |
| Frontend | list board + create card | edit, delete, drag-and-drop (no `svelte-dnd-action` dep yet) |
| Data | initial migration | seed-data migration |
| Ops | `docker-compose.yml` (local Postgres) | `tests/`, `Dockerfile`, `fly.toml`, `.github/workflows/` |

When extending the app, follow the plan already written in [docs/SHAPING.md](docs/SHAPING.md)
(§Detailed shape) and [docs/BREADBOARD.md](docs/BREADBOARD.md) — they define the target endpoints,
UI places, and mechanisms. Build in slices, matching the existing incremental style.

## Commands

Backend uses **`uv`** (Python 3.12; see [backend/pyproject.toml](backend/pyproject.toml) + `uv.lock`).
Frontend uses **`npm`** (Node 20+). Run backend commands from `backend/`, frontend from `frontend/`.

**Local database** (from repo root) — required before running the backend:
```bash
docker compose up -d db        # Postgres 16 at kanban:kanban@localhost:5432/kanban
```

**Backend** (from `backend/`):
```bash
uv sync                                        # install deps (incl. dev group)
uv run alembic upgrade head                    # apply migrations
uv run uvicorn app.main:app --reload           # dev server on :8000; OpenAPI at /docs
uv run alembic revision --autogenerate -m "…"  # new migration (models must be imported in env.py)
uv run pytest                                  # run tests (testpaths=["tests"]; none exist yet)
uv run pytest tests/test_x.py::test_name       # run a single test
```
> If `uv` is unavailable, a `python -m venv` + `pip install -e .` (or install from `pyproject.toml`)
> works too — the package is intentionally not installable (`tool.uv package = false`), so always
> run from `backend/` (`alembic.ini` sets `prepend_sys_path = .` so `import app` resolves).

**Frontend** (from `frontend/`):
```bash
npm ci            # install
npm run dev       # Vite dev server on :5173; proxies /api → http://localhost:8000
npm run build     # → frontend/dist (the bundle FastAPI serves in prod)
npm run check     # svelte-check type/lint pass (there is no separate ESLint)
```

**Full local dev loop:** `docker compose up -d db` → backend `uv run alembic upgrade head` +
`uvicorn … --reload` → frontend `npm run dev`, then open `:5173`.

## Configuration

`DATABASE_URL` is the only required runtime config. It defaults to the docker-compose Postgres:
`postgresql+psycopg://kanban:kanban@localhost:5432/kanban`. The **`+psycopg`** suffix selects the
psycopg **v3** driver — keep it. Both the app ([backend/app/db.py](backend/app/db.py)) and Alembic
([backend/alembic/env.py](backend/alembic/env.py)) read the same `DATABASE_URL`, so migrations
always target the app's database.

## Architecture (the big picture)

**Single deployable artifact, one origin.** In production FastAPI serves the built Svelte SPA as
static files with an SPA catch-all fallback (see [backend/app/main.py](backend/app/main.py):
`STATIC_DIR`, `spa_fallback`). The API router and `/docs` are registered *before* the catch-all so
they win. In local dev, Vite serves the SPA and proxies `/api` to the backend, so `STATIC_DIR`
typically doesn't exist and the fallback isn't registered — no CORS in either case.

**One table, no other entities.** The entire domain is the `card` table
([backend/app/models.py](backend/app/models.py)). Three mechanisms matter and are load-bearing:
- **Ticket number** `KAN-<n>`: assigned by a Postgres `SEQUENCE` via a column `server_default`
  (`'KAN-' || nextval('card_ticket_seq')`) — atomic at INSERT, immutable, never reused. The
  sequence is created in the initial migration, not by the ORM.
- **`column`** is a plain `varchar` guarded by a `CHECK` constraint (not a native PG enum), so
  adding a column value later needs no `ALTER TYPE` migration. Valid values live in three places
  that must stay in sync: `VALID_COLUMNS`/CHECK (models), `ColumnEnum` (schemas), `Column` (api.ts).
- **`position`** is a *relative sort key within a column*, not necessarily contiguous. Deletes
  intentionally leave gaps; a later move/reorder re-sequences via `renumber_column()`.

**Backend is deliberately flat** (Shape A "Thin Slice" — no service/repository layers):
`routers/cards.py` → `ordering.py` helper → `models.py`/`schemas.py`, with a `get_db()` FastAPI
dependency yielding a **synchronous** SQLAlchemy 2.0 session. Pydantic schemas
([backend/app/schemas.py](backend/app/schemas.py)) are the request/response contract and the
authoritative validation layer (title non-empty, `column` enum, `story_points ∈ {1,2,3,5,8,13}∪null`).

**Frontend is Svelte 5 runes.** [frontend/src/lib/board.svelte.ts](frontend/src/lib/board.svelte.ts)
is a single `$state` store; components read derived slices via `cardsFor(column)`.
[frontend/src/lib/api.ts](frontend/src/lib/api.ts) is a thin typed `fetch` wrapper that throws
`ApiError` on non-2xx. Component tree: `App → Board → Column → CardForm`.

**Server state is authoritative — no optimistic UI.** Every successful mutation is followed by a
`refetch()` of `GET /api/cards`; the UI never renders an order or value the server hasn't confirmed.
Preserve this pattern (it is a deliberate Shape A decision, [docs/BREADBOARD.md](docs/BREADBOARD.md) §7).

## Non-obvious conventions

- **API-first:** the UI must never do anything the API can't (R4.1 / ADR 0005). Add the endpoint
  first, then wire the UI to it. The API is being kept clean so future MCP/CLI/agent clients are
  thin adapters — this is the core motivation of the whole project.
- **Move vs. edit split:** column/position changes go through a dedicated `POST /api/cards/{id}/move`
  (not yet built); `PATCH` is for field edits only (title/description/story_points/assignee).
- **No auth, last-write-wins, no real-time** by design (ADR 0007) — don't add locking or websockets.
- **Neon free tier scales to zero**, so the first request after idle is slow (~1s) — that's a
  documented cold start, not a bug.

## How the docs relate (source of truth for intent)

This is a Shape Up project. The docs are a deliberate chain, not scratch notes — treat them as the
spec for intended behavior:

`REQS.md` (raw ask) → `FRAME.md` → `PRD.md` + [CONTEXT.md](docs/CONTEXT.md) (+ `adr/`) →
`SHAPING.md` (selects Shape A) → `BREADBOARD.md` (UI places & wiring) → build in slices.

- **[docs/CONTEXT.md](docs/CONTEXT.md)** — canonical glossary and domain model. Use these terms exactly.
- **[docs/adr/](docs/adr/)** (0001–0008, all Accepted) — the *why* behind each decision: monorepo &
  stack (0001), Postgres+Alembic from day one (0002), single-artifact serving (0003), Fly.io+Neon
  CI/CD (0004), API-first/MCP-ready (0005), data model (0006), no-auth/LWW/no-realtime (0007),
  sync-SQLAlchemy + psycopg v3 + varchar-CHECK column + Vite dev-proxy (0008).
