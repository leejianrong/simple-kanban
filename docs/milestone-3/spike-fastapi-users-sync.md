---
shaping: true
---

# Spike — fastapi-users on a sync SQLAlchemy app

## Context

Milestone 3 decision **D2** adopts [`fastapi-users`](https://fastapi-users.github.io/) for human
authentication (GitHub OAuth now; Google / email later) and **D3** builds a cookie-session backend
for humans + a bearer personal-access-token backend for agents on top of its `User` model.

But this app is **deliberately synchronous**: sync SQLAlchemy 2.0 `Session` + psycopg v3, with a
`get_db()` dependency yielding a sync session (ADR 0008). `fastapi-users` and its
`fastapi-users-db-sqlalchemy` adapter are **async-first** — the user-database methods are `async`
and expect an `AsyncSession`. Before we commit the auth shape we must know how the two coexist
without forcing a full-app rewrite (which ADR 0008 explicitly argued against).

## Goal

Identify the concrete, lowest-friction way to run fastapi-users' user store + auth backends against
our Postgres while the board/epic/card CRUD stays sync — and what that means for `db.py`, the
`get_db()` dependency, Alembic, and the auth router wiring.

## Questions

| # | Question |
|---|----------|
| **S1-Q1** | Does `fastapi-users` (current version) require an `AsyncSession`, or is there any supported sync path? What exactly is async — the user DB adapter, the auth backends, the route handlers, or all three? |
| **S1-Q2** | Can we stand up a **second, async** SQLAlchemy engine/session (`create_async_engine("postgresql+psycopg://…")`, psycopg v3 async) **alongside** the existing sync engine, both pointing at the same `DATABASE_URL` database? Any connection-pool or event-loop pitfalls running sync `Session` and `AsyncSession` in the same FastAPI app? |
| **S1-Q3** | If auth is async and board CRUD is sync, where's the seam? Do the auth routes (`/auth/*`, `/users/*`) use an async `get_async_db()` while the existing routers keep sync `get_db()`? Can both dependencies live in one app cleanly? |
| **S1-Q4** | Alternatively, is writing a **custom sync-backed `BaseUserDatabase`** adapter (async method signatures wrapping our sync session) viable and less trouble than a second engine? What methods must it implement? |
| **S1-Q5** | How do fastapi-users' tables (`user`, `oauth_account`) get created under **our Alembic** setup (models imported in `env.py`, autogenerate)? Do its declarative models compose with our `Base`, or need a separate metadata? |
| **S1-Q6** | Where does the **cookie-session** backend store sessions (its DB strategy / a `redis`/DB strategy), and is that strategy async too? Does revocable logout (D3) work with the chosen strategy? |
| **S1-Q7** | Do our **agent bearer tokens** (R4) fit as a fastapi-users *custom auth backend/transport*, or are they better built as our own dependency that resolves a token → `User` **outside** fastapi-users (fastapi-users owns human login only)? |
| **S1-Q8** | What's the GitHub OAuth flow wiring end to end (client id/secret config, callback route, associating an `oauth_account` with a `User`) and does it work behind the single-origin served-SPA setup (ADR 0003) with cookies? |

## Acceptance

Complete when we can describe: whether fastapi-users can run async-alongside-sync in this app (and
if so, the exact `db.py` / dependency / Alembic changes) or whether a custom sync adapter is the
better path; where agent tokens plug in; and how the GitHub cookie login flows end to end — enough
to write the M3 auth shape with **no ⚠️ flags left on the auth foundation**.

---

## Findings (investigated empirically — fastapi-users 15.0.5, db-adapter 7.0.0, psycopg 3.3, SQLAlchemy 2.0.51)

Verified against the live dev Postgres (scratch schemas, since dropped).

| # | Answer |
|---|--------|
| **S1-Q1** | fastapi-users' user store is **async-only** — every `SQLAlchemyUserDatabase` method (`get`, `create`, …) is a coroutine and it takes an `AsyncSession`. There is no supported sync path for the DB adapter. User ids are **UUID**. |
| **S1-Q2** | ✅ **Yes.** An async engine `create_async_engine("postgresql+psycopg://…")` (psycopg v3 async) runs against **the same** `DATABASE_URL` database; `SELECT 1` and a full user create+get round-trip work. A sync engine and an async engine coexist in one process against one DB with no issue (proven — see `probe_dual.py`). |
| **S1-Q3** | Seam is clean: **new async engine + `get_async_session()` dep for the auth/user routes only**; existing sync `get_db()` unchanged for board/epic/card routes. FastAPI mixes sync + async endpoints/deps natively. A `board` row (sync) FK-references a `user` row (async-created) in the same process — verified. |
| **S1-Q4** | A custom sync `BaseUserDatabase` is **not worth it** — its methods are async by contract, so a sync adapter still needs async signatures wrapping blocking calls (thread-pool or `asyncio.run` gymnastics). The second async engine (Q2) is strictly less code and idiomatic. **Rejected in favour of Q2.** |
| **S1-Q5** | ✅ fastapi-users models are SQLAlchemy **declarative mixins**; mixing them into **our existing `app.db.Base`** (already a 2.0 `DeclarativeBase`) yields **one shared metadata** — `user`, `oauth_account`, `board`, `personal_access_token` all autogenerate under **one Alembic pipeline** (import the models in `env.py`). No separate metadata needed. |
| **S1-Q6** | Revocable cookie sessions = `CookieTransport` + **`DatabaseStrategy`** backed by a `SQLAlchemyAccessTokenDatabase` (async, its own `access_token` table). Logout deletes the row → instant revocation. (Alternative `JWTStrategy` is stateless but not revocable — not chosen.) |
| **S1-Q7** | **Agent PATs are our own, not a fastapi-users backend.** fastapi-users' backends are for *human login sessions*; long-lived user-created tokens are a different concept. Build a `personal_access_token` table + a **sync** bearer dependency (evolves V4) that hashes the token, looks it up, resolves to a `User`. Bonus: agent auth stays **fully sync** — only human login touches the async engine. |
| **S1-Q8** | GitHub OAuth = `httpx_oauth.clients.github.GitHubOAuth2` + fastapi-users' `get_oauth_router` (both import fine). Flow: `/auth/github/authorize` → GitHub → same-origin `/callback` → creates/links `User`+`oauth_account`, `DatabaseStrategy` sets the `httpOnly` cookie. Single-origin (ADR 0003) means no CORS; client id/secret via env. |

### Resolved architecture (no ⚠️ left on the auth foundation)

- **One shared `Base`/metadata → one Alembic pipeline.** Auth models are mixins on `app.db.Base`.
- **Two engines, same DB:** keep the **sync** engine for all board/epic/card CRUD **and** the agent-PAT
  lookup (ADR 0008 preserved for the whole app surface); add an **async** engine used *only* by
  fastapi-users' human login/session/OAuth store.
- **Humans:** fastapi-users `CookieTransport` + `DatabaseStrategy` (revocable), GitHub OAuth router.
- **Agents:** our own hashed `personal_access_token` table + a sync bearer dep → `User` (evolves V4).
- **Both resolve to a `User` principal** → a single sync board-authorization check on the board routes.

**Acceptance met.** `spike*.py` probes archived in the session scratchpad; not committed.
