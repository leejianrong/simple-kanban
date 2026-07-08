# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first: what is and isn't built

The core board is **feature-complete and deployed** (live at
[simple-kanban-jian.fly.dev](https://simple-kanban-jian.fly.dev)): view / create / edit / delete /
drag-to-move all work end to end, behind a full REST API with an automated test suite (backend
pytest + frontend Playwright e2e) and CI/CD to Fly.io. The full "Shape A" plan is now implemented.
**Milestone 2 (Agent-Driven Task Tracking)** is now in progress — V1 (epic entity + story links)
has landed; V2–V5 (API versioning, query API, token auth, MCP server) are shaped but not
yet built (see the milestone table below and [docs/milestone-2/SLICES.md](docs/milestone-2/SLICES.md)).
The [docs/](docs/) folder describes those plans at a high level, so **don't assume a documented
detail matches the code** — check the source.

| Area | Built now | Documented but NOT yet built |
|------|-----------|------------------------------|
| API | `GET/POST /api/cards`, `GET/PATCH/DELETE /api/cards/{id}`, `POST /api/cards/{id}/move`; `GET/POST /api/epics`, `GET/PATCH/DELETE /api/epics/{id}`; `GET /api/health` | — |
| Ordering | `next_position()` (append to end), `renumber_column()` (re-sequence on move/reorder) | — |
| Frontend | `Board \| Epics` top-bar toggle. Board: list + create + edit + delete + drag-and-drop (`svelte-dnd-action`); each story shows its epic-name tag; epic selector in the story form. Epics view: create / list / edit / delete epics with a child-story rollup | — |
| Data | initial migration + demo seed-data migration (R0.4, `app/seed.py`, guarded to empty DBs); epic-entity migration `0003` (`epic` table + `EPIC-` sequence, nullable `card.epic_id` FK) | — |
| Ops | `docker-compose.yml` (Postgres + app), `Dockerfile`, `fly.toml`, `.github/workflows/` (CI + deploy), backend `tests/` (pytest unit + integration via testcontainers), frontend `e2e/` (Playwright smoke, in CI) | — |

**Milestone 2 slices** (see [docs/milestone-2/SLICES.md](docs/milestone-2/SLICES.md)):

| Slice | What | Status |
|-------|------|--------|
| V1 | Epic as a first-class entity (`epic` table + `EPIC-`, `card.epic_id`) + Epics view / story tags (ADR 0009) | **Built** |
| V2 | API versioning (`/api/v1` + `/api` alias) | Not yet built |
| V3 | Query API (filter / pagination / changed-since) | Not yet built |
| V4 | Agent token auth on writes (`API_TOKENS`) | Not yet built |
| V5 | MCP server (`/mcp`, stdio) + Claude Code wiring | Not yet built |

When extending the app, follow the plan already written in [docs/SHAPING.md](docs/SHAPING.md)
(§Detailed shape) and [docs/BREADBOARD.md](docs/BREADBOARD.md) for the core board, and
[docs/milestone-2/](docs/milestone-2/) for the agent milestone — they define the target endpoints,
UI places, and mechanisms. Build in slices, matching the existing incremental style.

## Commands

Backend uses **`uv`** (Python 3.12; see [backend/pyproject.toml](backend/pyproject.toml) + `uv.lock`).
Frontend uses **`npm`** (Node 20+). Run backend commands from `backend/`, frontend from `frontend/`.

**Local database** (from repo root) — required before running the backend:
```bash
docker compose up -d db        # Postgres 17 at kanban:kanban@localhost:5432/kanban
```

**Backend** (from `backend/`):
```bash
uv sync                                        # install deps (incl. dev group)
uv run alembic upgrade head                    # apply migrations
uv run uvicorn app.main:app --reload           # dev server on :8000; OpenAPI at /docs
uv run alembic revision --autogenerate -m "…"  # new migration (models must be imported in env.py)
uv run ruff check .                            # lint (matches the CI lint job)
uv run pytest tests/unit                       # fast: pure schema-validation logic, no DB/Docker
uv run pytest tests/integration                # full API vs a throwaway Postgres (needs a running Docker daemon)
uv run pytest tests/integration/test_x.py::test_name  # run a single test
```
> Tests are split into `tests/unit` (no DB) and `tests/integration` (real Postgres via
> testcontainers); the integration `client`/DB fixtures live in `tests/integration/conftest.py`,
> so integration tests must live under `tests/integration/`. CI runs lint, unit, integration, the
> frontend build, and Playwright e2e as five independent jobs (see `.github/workflows/ci.yml`); the
> e2e job uses a Postgres service container and caches the Chromium download by Playwright version.
> If `uv` is unavailable, a `python -m venv` + `pip install -e .` (or install from `pyproject.toml`)
> works too — the package is intentionally not installable (`tool.uv package = false`), so always
> run from `backend/` (`alembic.ini` sets `prepend_sys_path = .` so `import app` resolves).

**Frontend** (from `frontend/`):
```bash
npm ci            # install
npm run dev       # Vite dev server on :5173; proxies /api → http://localhost:8000
npm run build     # → frontend/dist (the bundle FastAPI serves in prod)
npm run check     # svelte-check type/lint pass (there is no separate ESLint)
npm run e2e       # Playwright smoke (auto-starts backend+Vite; needs docker compose up -d db)
```
> Playwright e2e specs live in `frontend/e2e/`. The config's `webServer` boots the FastAPI backend
> (:8000) and Vite (:5173) itself, but a local Postgres must already be up (`docker compose up -d db`).
> One-time browser install: `npx playwright install chromium`. Tests prefix their cards with `e2e-`
> and clean up after themselves, so they tolerate existing dev data. Runs in CI as the `e2e` job.

**Full local dev loop:** `docker compose up -d db` → backend `uv run alembic upgrade head` +
`uvicorn … --reload` → frontend `npm run dev`, then open `:5173`.

## Development workflow (conventions — for humans and agents)

**Branch per change, off a fresh `main`.** `main` is protected: direct pushes are rejected and
every change lands via PR only after CI (lint + unit + integration + frontend build) is green.
Always start from an up-to-date `main`:
```bash
git switch main && git pull --ff-only
git switch -c feat/<slice>        # one branch per vertical slice, matching the Shape Up cadence
```
When merging a PR that carries commits you want to preserve (e.g. an external contributor's from a
fork), **merge with a merge commit, not squash** — that keeps per-commit authorship and lets the
contributor's fork PR auto-close as *merged*. Delete the branch (local + remote) once it's merged.
> Integrating a fork branch that predates `main`: fetch it into a review branch and merge it into an
> integration branch built on current `main` (resolve conflicts there, keep it a true merge so the
> contributor's commits survive), then PR that integration branch → `main`. See PRs #2/#5 for the
> worked example.

**Use git worktrees for parallel work — this is the expected workflow here.** Instead of stashing or
switching branches in place, give each in-flight task its own directory backed by the one clone, so
your primary checkout stays undisturbed while you review a contributor PR, hotfix, or spike:
```bash
git worktree add ../simple-kanban-<slice> -b feat/<slice> main   # new feature in its own dir
git worktree add ../simple-kanban-review review/<name>           # review someone else's branch
git worktree list                                                # see them all
git worktree remove ../simple-kanban-<slice>                     # clean up when merged
```
Each worktree needs its own `backend/.venv` (`uv sync`) and `frontend/node_modules` (`npm ci`); the
Postgres from `docker compose up -d db` is shared across all of them. Agents should prefer the
harness's built-in worktree isolation (`isolation: "worktree"`) for parallel file-mutating work.

**Pre-push hook.** `scripts/git-hooks/pre-push` (tracked) runs the fast CI checks locally — ruff +
`tests/unit` + `svelte-check` — so a push never lands red. Integration tests stay CI-only (they need
a Docker daemon). Hooks aren't auto-installed; install once per clone (it lives in the shared
`.git/hooks`, so linked worktrees inherit it automatically):
```bash
ln -sf ../../scripts/git-hooks/pre-push .git/hooks/pre-push
```
Bypass a single push with `git push --no-verify` (use sparingly).

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

**Two tables: `card` (a story on the board) and `epic`** ([backend/app/models.py](backend/app/models.py)).
Milestone 2 V1 promoted the epic to a **first-class entity** (ADR 0009) — it is *not* a card. These
mechanisms matter and are load-bearing:
- **Ticket numbers** are per-table `SEQUENCE`s via a column `server_default`, atomic at INSERT,
  immutable, never reused: cards get `KAN-<n>` (`card_ticket_seq`), epics get `EPIC-<n>`
  (`epic_ticket_seq`). Independent — `KAN-1` and `EPIC-1` coexist. Sequences are created in the
  migrations, not by the ORM.
- **`column`** is a plain `varchar` guarded by a `CHECK` constraint (not a native PG enum), so
  adding a column value later needs no `ALTER TYPE` migration. Valid values live in three places
  that must stay in sync: `VALID_COLUMNS`/CHECK (models), `ColumnEnum` (schemas), `Column` (api.ts).
- **`epic`** carries only `name` + optional `description` — **no** column/position/assignee/
  story_points (an epic is board-less and unestimated). A story links to zero-or-one epic via the
  nullable **`card.epic_id`** FK → `epic.id` (`ON DELETE SET NULL`, so deleting an epic detaches its
  stories rather than blocking or cascading). That `epic_id` references an existing epic is enforced
  in `routers/cards.py` (`_validate_epic`, 422) on POST/PATCH. Epics have their own CRUD router
  ([backend/app/routers/epics.py](backend/app/routers/epics.py)) and are managed in a separate UI view.
- **`position`** is a *relative sort key within a column*, not necessarily contiguous. Deletes
  intentionally leave gaps; a move/reorder re-sequences the affected column(s) via `renumber_column()`.

**Backend is deliberately flat** (Shape A "Thin Slice" — no service/repository layers):
`routers/cards.py` (+ `routers/epics.py`) → `ordering.py` helper → `models.py`/`schemas.py`, with a
`get_db()` FastAPI dependency yielding a **synchronous** SQLAlchemy 2.0 session. Pydantic schemas
([backend/app/schemas.py](backend/app/schemas.py)) are the request/response contract and the
authoritative validation layer (title/name non-empty, `column` enum, `story_points ∈ {1,2,3,5,8,13}∪null`).

**Frontend is Svelte 5 runes.** [frontend/src/lib/board.svelte.ts](frontend/src/lib/board.svelte.ts)
holds the `$state` stores (`board` cards + `epicStore`); components read derived slices via
`cardsFor(column)` / `epicFor(id)` / `cardsForEpic(id)`.
[frontend/src/lib/api.ts](frontend/src/lib/api.ts) is a thin typed `fetch` wrapper that throws
`ApiError` on non-2xx. `App` shows a `Board | Epics` toggle (no router). Board tree:
`Board → Column → Card → CardForm` (`Card` owns view / edit / confirm-delete; `CardForm` handles
create and edit, incl. the epic selector). Epics tree: `Epics → EpicItem → EpicForm` (same
view/edit/delete shape). `Column` wraps its cards in a `svelte-dnd-action` dropzone; on
`DROPPED_INTO_ZONE` it calls `moveCard(id, {column, position})` and the usual `refetch()` reconciles.

**Server state is authoritative — no optimistic UI.** Every successful mutation is followed by a
`refetch()` (`GET /api/cards`) / `refetchEpics()`; the UI never renders a value the server hasn't confirmed.
Preserve this pattern (it is a deliberate Shape A decision, [docs/BREADBOARD.md](docs/BREADBOARD.md) §7).

## Non-obvious conventions

- **API-first:** the UI must never do anything the API can't (R4.1 / ADR 0005). Add the endpoint
  first, then wire the UI to it. The API is being kept clean so future MCP/CLI/agent clients are
  thin adapters — this is the core motivation of the whole project.
- **Move vs. edit split:** column/position changes go through the dedicated `POST /api/cards/{id}/move`
  (append to target column, clamp to a requested index, and `renumber_column()` the source); `PATCH`
  is for field edits only (title/description/story_points/assignee).
- **No auth, last-write-wins, no real-time** by design (ADR 0007) — don't add locking or websockets.
- **Neon free tier scales to zero**, so the first request after idle is slow (~1s) — that's a
  documented cold start, not a bug.

## How the docs relate (source of truth for intent)

This is a Shape Up project. The docs are a deliberate chain, not scratch notes — treat them as the
spec for intended behavior:

`REQS.md` (raw ask) → `FRAME.md` → `PRD.md` + [CONTEXT.md](docs/CONTEXT.md) (+ `adr/`) →
`SHAPING.md` (selects Shape A) → `BREADBOARD.md` (UI places & wiring) → build in slices.

- **[docs/CONTEXT.md](docs/CONTEXT.md)** — canonical glossary and domain model. Use these terms exactly.
- **[docs/adr/](docs/adr/)** (0001–0009, all Accepted) — the *why* behind each decision: monorepo &
  stack (0001), Postgres+Alembic from day one (0002), single-artifact serving (0003), Fly.io+Neon
  CI/CD (0004), API-first/MCP-ready (0005), data model (0006), no-auth/LWW/no-realtime (0007),
  sync-SQLAlchemy + psycopg v3 + varchar-CHECK column + Vite dev-proxy (0008), epic as a first-class
  entity — separate `epic` table + `EPIC-` sequence, evolving 0006's one-table stance (0009).
