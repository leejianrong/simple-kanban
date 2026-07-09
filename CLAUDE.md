# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first: what is and isn't built

The core board is **feature-complete and deployed** (live at
[simple-kanban-jian.fly.dev](https://simple-kanban-jian.fly.dev)): view / create / edit / delete /
drag-to-move all work end to end, behind a full REST API with an automated test suite (backend
pytest + frontend Playwright e2e) and CI/CD to Fly.io. The full "Shape A" plan is now implemented.
**Milestone 2 (Agent-Driven Task Tracking)** is now **feature-complete** — all five slices landed:
V1 (epic entity + story links), V2 (API versioning), V3 (query API), V4 (token auth), and V5 (the
MCP server in [mcp/](mcp/) + Claude Code wiring). See the milestone table below and
[docs/milestone-2/SLICES.md](docs/milestone-2/SLICES.md).
**Milestone 3 (Accounts, Boards & Agent Access)** is now **feature-complete** — all five slices
landed: **V6 (human GitHub login, ADR 0011)**, **V7 (multi-board with ownership, ADR 0012)**, **V8
(board authorization, ADR 0013)**, **V9 (self-serve agent PATs, ADR 0014)**, and **V10 (MCP
board-scoping + retiring `API_TOKENS`, ADR 0015)** are all **built**. **V8 flipped `/api/v1` from
open to auth-required and owner-gated:** every board-scoped route resolves a principal and allows
only the board's owner (else `403`); lists are owner-scoped; first login claims unclaimed boards.
**V9 added per-user hashed PATs** to that resolver. **V10 board-scoped the MCP server** (per-call
`board_id` + `list_boards`/`create_board`/`list_epics` tools + optional `KANBAN_BOARD_ID`) and
**removed the transitional `API_TOKENS` SERVICE bypass**, so the principal resolver is now exactly
**cookie session → `User`; else PAT bearer → its owning `User`; else `401`** — every principal is a
real `User`, owner-gated identically. `API_TOKENS` is gone (ADR 0010 fully retired).
The [docs/](docs/) folder describes those plans at a high level, so **don't assume a documented
detail matches the code** — check the source.

| Area | Built now | Documented but NOT yet built |
|------|-----------|------------------------------|
| API | Canonical `/api/v1` (V2): `GET/POST /api/v1/cards`, `GET/PATCH/DELETE /api/v1/cards/{id}`, `POST /api/v1/cards/{id}/move`; `GET/POST /api/v1/epics`, `GET/PATCH/DELETE /api/v1/epics/{id}`; `GET/POST /api/v1/boards`, `GET/PATCH/DELETE /api/v1/boards/{id}` (V7); unversioned `GET /api/health`. `GET /api/v1/cards` takes query params `board_id`/`column`/`epic_id`/`updated_since`/`limit`/`cursor` with keyset pagination via the `X-Next-Cursor` header (V3); `GET /api/v1/epics` takes `board_id`. Card/epic create takes optional `board_id` (defaults to the earliest board). `GET/POST /api/v1/tokens`, `DELETE /api/v1/tokens/{id}` (V9 agent PATs). **Owner-gated (V8, ADR 0013; V10, ADR 0015):** every board-scoped route is auth-required — a cookie session (→`User`) or a **PAT bearer** (→owning `User`, V9), else `401`; non-owner → `403`; lists owner-scoped. A story's epic must be on the same board (422) | — |
| Boards (M3 V7 + V8 authz) | `board` table (`name` + nullable `owner_id`→user); NOT NULL `board_id` on card+epic (ON DELETE CASCADE); `/api/v1/boards` CRUD (owner from session, cascade delete). Migration `0005` seeds one default board + backfills existing cards/epics; **first login claims unclaimed boards** (V8, `UserManager.on_after_login`). Owner-only authz + list scoping enforced (V8, `app/authz.py`). Positions are per (board, column). Ticket numbers stay global `KAN-`/`EPIC-` (ADR 0012/0013) | — |
| Auth (M3 V6 + V8 + V9) | Human login: unversioned `GET /auth/github/authorize` + `/auth/github/callback` (GitHub OAuth, **only mounted when creds are set**), `POST /auth/logout`, `GET/PATCH /users/me`. Revocable httpOnly cookie session (fastapi-users `CookieTransport` + `DatabaseStrategy`). `User`/`OAuthAccount`/`access_token` tables on a second **async** engine (ADR 0011). **Board authz** (`app/authz.py`, V8): sync principal resolver + `authorize_board`. **Agent PATs** (V9, ADR 0014): `personal_access_token` table (migration `0006`), hashed HMAC-SHA256 (`app/tokens.py`), a sync PAT branch in the resolver → owning `User`; managed via `/api/v1/tokens`. **V10 (ADR 0015) removed the `API_TOKENS` SERVICE bypass** — the resolver is cookie-or-PAT-or-401, every principal a real `User`. **E2E-only** `POST /auth/test-login` when `E2E_AUTH_BYPASS` set (never in prod) | — |
| Frontend auth | `Landing.svelte` for logged-out visitors (from the mockup, `.landing`-scoped tokens, light/dark); `App.svelte` gates on `GET /users/me` (401 → landing, else board); top-bar shows the user email + **Log out**. Same-origin fetches carry the session cookie, so the now-owner-gated `/api/v1` works; `refetchBoards()` scopes to owned boards (a new user with none sees an empty board + switcher). Top-bar **Tokens** view (`Tokens.svelte` + `tokens.svelte.ts`, V9): create / reveal-once / revoke agent PATs | — |
| Frontend boards | Top-bar **board switcher** (`BoardSwitcher.svelte`): select / new / rename / delete; active board persisted in localStorage; card + epic views/creates scope to it (`boardStore` in board.svelte.ts) | — |
| Ordering | `next_position()` (append to end), `renumber_column()` (re-sequence on move/reorder) | — |
| Frontend | `Board \| Epics` top-bar toggle. Board: list + create + edit + delete + drag-and-drop (`svelte-dnd-action`); each story shows its epic-name tag; epic selector in the story form. Epics view: create / list / edit / delete epics with a child-story rollup | — |
| Data | initial migration + demo seed-data migration (R0.4, `app/seed.py`, guarded to empty DBs); epic-entity migration `0003` (`epic` table + `EPIC-` sequence, nullable `card.epic_id` FK) | — |
| Ops | `docker-compose.yml` (Postgres + app), `Dockerfile`, `fly.toml`, `.github/workflows/` (CI + deploy), backend `tests/` (pytest unit + integration via testcontainers), frontend `e2e/` (Playwright smoke, in CI) | — |

**Milestone 2 slices** (see [docs/milestone-2/SLICES.md](docs/milestone-2/SLICES.md)):

| Slice | What | Status |
|-------|------|--------|
| V1 | Epic as a first-class entity (`epic` table + `EPIC-`, `card.epic_id`) + Epics view / story tags (ADR 0009) | **Built** |
| V2 | API versioning: all routers under `/api/v1` (the temporary `/api` compat alias has been dropped; `/api/health` stays unversioned) | **Built** |
| V3 | Query API on `GET /api/v1/cards` (`column`/`epic_id`/`updated_since`/`limit`/`cursor`; keyset pagination via `X-Next-Cursor`; `app/pagination.py`) | **Built** |
| V4 | Agent token auth on writes — `require_token` dep + `API_TOKENS` (ADR 0010). **Superseded by V9 PATs and fully retired in V10** (ADR 0015): the `API_TOKENS` mechanism no longer exists | **Superseded** |
| V5 | MCP server (`mcp/`, official `mcp` SDK/FastMCP, stdio) — thin httpx wrapper over `/api/v1`; `.mcp.json.example` + `mcp/README.md` for Claude Code (board-scoped in V10) | **Built** |

**Milestone 3 slices** (see [docs/milestone-3/SLICES.md](docs/milestone-3/SLICES.md)):

| Slice | What | Status |
|-------|------|--------|
| V6 | Human login: fastapi-users on a second **async** engine; GitHub OAuth + revocable cookie session; `Landing.svelte` + `GET /users/me` auth-gated SPA + logout (ADR 0011) | **Built** |
| V7 | Boards as a first-class entity (`board` table, `card`/`epic` `board_id`), board switcher, default-board migration (ADR 0012) | **Built** |
| V8 | Board authorization — `/api/v1` owner-gated (principal resolver + `authorize_board`, list scoping + 403); claim-on-login; `API_TOKENS`→SERVICE bypass; same-board epic rule (ADR 0013) | **Built** |
| V9 | Self-serve agent personal-access-tokens (hashed HMAC-SHA256, `personal_access_token` + migration `0006`, `/api/v1/tokens`, Tokens UI); PAT branch in the resolver → owning user; supersedes V4's `API_TOKENS` as the agent mechanism (ADR 0014) | **Built** |
| V10 | MCP board-scoping (per-call `board_id` + `list_boards`/`create_board`/`list_epics` tools + `KANBAN_BOARD_ID`) + PAT auth; removed the transitional `API_TOKENS` SERVICE bypass (ADR 0015) | **Built** |

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
> so integration tests must live under `tests/integration/`. **In integration tests, keep every
> `import app.*` inside the test/fixture body, never at module top** — a top-level app import runs at
> pytest collection (before the `_database` fixture sets `DATABASE_URL`), binding the engines to the
> wrong DB; it passes locally against your dev Postgres but fails CI (the PR #17 trap). A
> `pytest_collection_finish` guard in conftest + a `pytest --collect-only` step in the pre-push hook
> now catch this. CI runs lint, unit, integration, the
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

**MCP server** (from `mcp/`) — the agent entry point (V5, board-scoped in V10), its own `uv` package:
```bash
uv sync                                             # install (mcp SDK + httpx)
uv run ruff check .                                 # lint (matches CI mcp job)
uv run pytest -q                                    # unit (mocked httpx) + tool-list smoke; no DB
KANBAN_API_URL=http://localhost:8000 KANBAN_TOKEN=kanban_pat_… uv run python -m kanban_mcp   # run the stdio server by hand
```
> Thin `httpx` wrapper over `/api/v1` — 10 tools (`list_boards`/`create_board` discovery +
> board-scoped card/epic tools), no DB of its own. Config via `KANBAN_API_URL` + `KANBAN_TOKEN` (a
> **required** per-user PAT since `/api/v1` is auth-required) + optional `KANBAN_BOARD_ID` (default
> board for calls that omit `board_id`; V10, ADR 0015). Wire into Claude Code by copying
> `.mcp.json.example` → `.mcp.json`; see [mcp/README.md](mcp/README.md). CI runs it as the `mcp` job.

**Full local dev loop:** `docker compose up -d db` → backend `uv run alembic upgrade head` +
`uvicorn … --reload` → frontend `npm run dev`, then open `:5173`.

## Development workflow (conventions — for humans and agents)

**Branch per change, off a fresh `main`.** `main` is protected: direct pushes are rejected and
every change lands via PR only after CI (lint + unit + integration + frontend build + e2e + mcp) is green.
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

**Agent auth is a per-user PAT (V9, ADR 0014; V10, ADR 0015).** `/api/v1` is **auth-required** for
every request. Agents (the MCP server, `curl`) authenticate with a self-serve per-user **PAT**
(`kanban_pat_…`, hashed HMAC-SHA256; created/revoked at `/api/v1/tokens` + the Tokens UI) set as
`KANBAN_TOKEN`; it resolves to its owning user and is **owner-gated** exactly like a human. The
SPA/human clients authenticate with the **cookie session** and send no token. **`API_TOKENS` no
longer exists** — V4's shared-token list (ADR 0010) was superseded by PATs (V9) and its transitional
SERVICE bypass was removed in V10 (ADR 0015). (Ops: the `API_TOKENS` Fly secret can be dropped.)

`AUTH_SECRET` doubles as the **pepper** for PAT hashing (HMAC-SHA256), so rotating it invalidates all
existing PATs (and cookie sessions) — expected.

`E2E_AUTH_BYPASS` (V8) — when truthy, mounts an **e2e-only** `POST /auth/test-login` that mints a
real cookie session for an arbitrary email (Playwright can't fake the httpOnly session a
route-stub used to). **Never set in prod** — it's a login bypass. The Playwright `webServer` sets it;
the e2e cleanup helpers reuse it to act **as each owning user** (V10 removed the SERVICE bearer they
used to use).

**Human auth env vars (M3 V6, ADR 0011)** — all read at import time in [backend/app/users.py](backend/app/users.py):
- `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` — GitHub OAuth App credentials. **Both
  unset → the GitHub login routes don't register** and the app still boots (landing shows, login
  unavailable). Set both to enable login. The OAuth App's callback URL is
  `<origin>/auth/github/callback` (dev: `http://localhost:5173/auth/github/callback`, proxied to
  :8000; prod: `https://<host>/auth/github/callback`). A GitHub OAuth App allows only **one** callback
  URL, so dev and prod use **separate** OAuth Apps. Prod runs behind Fly's TLS-terminating proxy, so
  the `Dockerfile` starts uvicorn with `--proxy-headers --forwarded-allow-ips=*` — without it the
  generated `redirect_uri` is `http://` and GitHub rejects the mismatch.
- `AUTH_SECRET` — signs session/OAuth-state tokens. Has an **insecure dev default**; prod **must**
  set a strong random value (Fly secret).
- `COOKIE_SECURE` — `1`/`true` to mark session + CSRF cookies `Secure` (HTTPS-only). Off by default
  (dev + tests run over http); set in prod.

These are separate from the sync board API: only human login touches the async engine. Board
reads/writes **are** user-gated as of V8 (ADR 0013) — the sync board routes depend on the async
`current_optional_user` to resolve the human principal, then check board ownership (`app/authz.py`).

## Architecture (the big picture)

**Single deployable artifact, one origin.** In production FastAPI serves the built Svelte SPA as
static files with an SPA catch-all fallback (see [backend/app/main.py](backend/app/main.py):
`STATIC_DIR`, `spa_fallback`). The API router and `/docs` are registered *before* the catch-all so
they win. In local dev, Vite serves the SPA and proxies `/api` to the backend, so `STATIC_DIR`
typically doesn't exist and the fallback isn't registered — no CORS in either case.

**Three tables: `board`, `card` (a story on a board) and `epic`** ([backend/app/models.py](backend/app/models.py)).
Milestone 2 V1 promoted the epic to a **first-class entity** (ADR 0009) — it is *not* a card;
Milestone 3 V7 promoted the board likewise (ADR 0012, evolving 0006's implicit single board). Every
card + epic has a NOT NULL `board_id` FK → `board` (`ON DELETE CASCADE`); `board.owner_id` → `user`
is nullable (`ON DELETE SET NULL`). These mechanisms matter and are load-bearing:
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
- **`position`** is a *relative sort key within a (board, column)*, not necessarily contiguous
  (since V7 ordering is per board). Deletes intentionally leave gaps; a move/reorder re-sequences the
  affected board+column(s) via `renumber_column()` — `next_position`/`renumber_column` take `board_id`.

**Two engines, one database (M3 V6, ADR 0011).** The board is **sync** (ADR 0008): a `get_db()`
dependency yields a synchronous session for all card/epic CRUD. Human auth (fastapi-users) needs an
**async** store, so [backend/app/db.py](backend/app/db.py) also builds a **second, async** engine
(`async_engine` / `get_async_session`) used **only** by the auth routes — same `DATABASE_URL`, same
psycopg v3 driver, same shared `Base`/metadata (so one Alembic pipeline covers `card`/`epic` **and**
`user`/`oauth_account`/`access_token`; auth models live in [backend/app/auth_models.py](backend/app/auth_models.py),
imported in `alembic/env.py`). Auth wiring is in [backend/app/users.py](backend/app/users.py). Don't
route board CRUD through the async engine — the sync path is deliberate and load-bearing.

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
`refetch()` (`GET /api/v1/cards`) / `refetchEpics()`; the UI never renders a value the server hasn't confirmed.
Preserve this pattern (it is a deliberate Shape A decision, [docs/BREADBOARD.md](docs/BREADBOARD.md) §7).

## Non-obvious conventions

- **API-first:** the UI must never do anything the API can't (R4.1 / ADR 0005). Add the endpoint
  first, then wire the UI to it. The API is being kept clean so future MCP/CLI/agent clients are
  thin adapters — this is the core motivation of the whole project.
- **Move vs. edit split:** column/position changes go through the dedicated `POST /api/v1/cards/{id}/move`
  (append to target column, clamp to a requested index, and `renumber_column()` the source); `PATCH`
  is for field edits only (title/description/story_points/assignee).
- **Last-write-wins, no real-time** by design (ADR 0007) — don't add locking or websockets. Auth
  was originally "none" (ADR 0007); V4 added optional bearer-token auth on writes (ADR 0010); **M3
  V6 added human GitHub login** with a first-class `User` + revocable cookie session (ADR 0011); V7
  added **multi-board with ownership** (ADR 0012). **V8 (ADR 0013) made `/api/v1` auth-required and
  owner-gated** — every board-scoped route resolves a principal in `app/authz.py` and allows only
  the board's owner (else `403`); lists are owner-scoped; the V4 `require_token` write-guard is gone
  (folded in). **V9 (ADR 0014) added self-serve per-user PATs** as the resolver's agent branch, and
  **V10 (ADR 0015) removed the transitional `API_TOKENS` SERVICE bypass**, so the resolver is now
  simply cookie session → `User`; else PAT bearer → its owning `User`; else `401` — **every principal
  is a real `User`**, owner-gated identically. Route authz goes through `get_principal` +
  `authorize_board` (`require_user` is now just an alias of `get_principal` for per-user routes like
  `/api/v1/tokens`) — don't add an ad-hoc check.
- **Neon free tier scales to zero**, so the first request after idle is slow (~1s) — that's a
  documented cold start, not a bug.

## How the docs relate (source of truth for intent)

This is a Shape Up project. The docs are a deliberate chain, not scratch notes — treat them as the
spec for intended behavior:

`REQS.md` (raw ask) → `FRAME.md` → `PRD.md` + [CONTEXT.md](docs/CONTEXT.md) (+ `adr/`) →
`SHAPING.md` (selects Shape A) → `BREADBOARD.md` (UI places & wiring) → build in slices.

- **[docs/CONTEXT.md](docs/CONTEXT.md)** — canonical glossary and domain model. Use these terms exactly.
- **[docs/adr/](docs/adr/)** (0001–0015; all Accepted except 0010, superseded) — the *why* behind each decision: monorepo &
  stack (0001), Postgres+Alembic from day one (0002), single-artifact serving (0003), Fly.io+Neon
  CI/CD (0004), API-first/MCP-ready (0005), data model (0006), no-auth/LWW/no-realtime (0007),
  sync-SQLAlchemy + psycopg v3 + varchar-CHECK column + Vite dev-proxy (0008), epic as a first-class
  entity — separate `epic` table + `EPIC-` sequence, evolving 0006's one-table stance (0009),
  optional bearer-token auth on writes (`API_TOKENS`), evolving 0007's no-auth stance (0010),
  human GitHub login + revocable cookie sessions via fastapi-users on a second async engine, further
  evolving 0007 (0011), multi-board with ownership — `board` table + `board_id` on card/epic,
  evolving 0006's single-board stance (0012), board authorization — `/api/v1` becomes auth-required
  + owner-gated (principal resolver + `authorize_board`, claim-on-login, `API_TOKENS`→SERVICE
  bypass), realising D3's one authorization layer and further evolving 0007/0010 (0013), self-serve
  agent personal access tokens — per-user hashed PATs resolving to their owning user, superseding
  0010's shared `API_TOKENS` as the agent mechanism (0014), MCP board-scoping (per-call `board_id` +
  `list_boards`/`create_board` discovery + `KANBAN_BOARD_ID`) and **retiring `API_TOKENS`** — removing
  the transitional SERVICE bypass so every principal is a real user, fully superseding 0010 (0015).
