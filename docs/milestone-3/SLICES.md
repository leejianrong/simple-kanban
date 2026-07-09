---
shaping: true
---

# Milestone 3 — Slices (Shape A)

Vertical increments of the [breadboard](BREADBOARD.md). Each ends in **observable behaviour** and
ships as its own PR behind CI, matching the M1/M2 cadence. Numbering **continues the global
V-series** (M2 was V1–V5) so branch/PR references stay unambiguous: M3 is **V6–V10**.

Order respects dependencies: login (V6) is the foundation everything hangs off; boards (V7) need a
user to own them; authz (V8) needs boards; tokens (V9) need a user + board authz; MCP scoping (V10)
needs boards + tokens.

| Slice | What | Ends in (demo) |
|-------|------|----------------|
| **V6 · Human login + landing** ✅ **Built** | A1, A2, A3, A9 | Logged out → the landing page; "Sign in with GitHub" → OAuth → your board; reload stays in; log out → landing |
| **V7 · Boards** ✅ **Built** | A4, A8 | Create a second board and switch between them; existing cards/epics live in a migrated default board |
| **V8 · Board authorization** ✅ **Built** | A5 | User A gets `403` on user B's board (API + UI); your own boards work; lists show only your boards |
| **V9 · Agent tokens** ✅ **Built** | A6 | Create a named token in the UI (shown once), write to your board via `curl` with it, revoke it → `401` |
| **V10 · MCP board-scoping** ✅ **Built** | A7 | Claude, via MCP with a PAT, creates/moves cards on a chosen board — and can't touch another user's board |

---

## V6 · Human login + landing ✅ Built

> **Built** (ADR 0011). fastapi-users 15.x on a second **async** engine beside the sync app;
> `user`/`oauth_account`/`access_token` tables (migration `0004`); GitHub OAuth cookie sessions
> (`CookieTransport` + `DatabaseStrategy`, revocable); `Landing.svelte` + `GET /users/me` auth-gated
> SPA routing + top-bar logout. Two build-revealed details vs. the plan: the authorize endpoint
> returns JSON (so the CTA fetches-then-navigates) and a `RedirectCookieTransport` bounces the OAuth
> callback back to `/` (see ADR 0011 §Build-revealed detail). `/api/v1` is **not** yet user-gated —
> that is V8. New env: `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`, `AUTH_SECRET`,
> `COOKIE_SECURE`.

- **Build:** add fastapi-users `User`/`OAuthAccount`/`access_token` models as mixins on `app.db.Base`;
  a **second async engine** + `get_async_session()` (sync engine unchanged, ADR 0008); Alembic
  migration creating the auth tables. GitHub OAuth router (`httpx-oauth` `GitHubOAuth2`) +
  `CookieTransport` + `DatabaseStrategy` (revocable httpOnly cookie) + users router. Provider
  modularity (A3) falls out of the fastapi-users backend/OAuth-client config — Google/email later is
  registration, not rework. SPA: `Landing.svelte` (from the mockup) shown when logged out; the board
  when logged in; an auth check (`GET /users/me`) picks which; top-bar user + **Log out**.
- **Tests:** integration — unauthenticated `/users/me` → 401; the OAuth callback creates a `User` +
  `OAuthAccount` and sets a session cookie; logout revokes it (mock the GitHub token exchange).
  e2e — logged-out shows the landing; a stubbed login lands on the board and survives reload; logout
  returns to the landing.
- **Acceptance:** the login/landing demo works; full suite green. **Config:** `GITHUB_OAUTH_CLIENT_ID`
  / `GITHUB_OAUTH_CLIENT_SECRET` + a session secret (Fly secrets in prod).

## V7 · Boards ✅ Built

> **Built** (ADR 0012). `board` table (`name` + nullable `owner_id`→user, ON DELETE SET NULL); NOT
> NULL `board_id` on card + epic (ON DELETE CASCADE); `/api/v1/boards` CRUD; migration `0005` seeds
> one **unclaimed** default board and backfills all existing cards/epics into it. Positions are now
> per (board, column). SPA gains a top-bar **board switcher** (select / new / rename / delete) with
> the active board persisted in localStorage; card/epic views + creates scope to it. `board_id` is
> **optional on create** (defaults to the earliest board) so the MCP server + older clients keep
> working. **No authorization yet** — any request can touch any board; owner-only enforcement is V8.
> Two build decisions (confirmed with the maintainer): the default board is **unclaimed** (nullable
> owner, no bootstrap user) and deleting a board **cascades** its cards/epics.

- **Build:** `board` table (`id`, `name`, `owner_id`→`user`); nullable→backfilled `card.board_id` /
  `epic.board_id` FKs; `/api/v1/boards` CRUD. **Migration (A8):** create a default board owned by the
  first/bootstrap user and attach all existing cards/epics to it (no data loss). SPA: a **board
  switcher** in the top bar (list, select, create, rename, delete); the board view reads the selected
  `board_id`. Ticket numbers stay **global** `KAN-`/`EPIC-` (D4).
- **Tests:** integration — board CRUD; a new card/epic is created under the active board; the
  migration attaches legacy rows to the default board; `board_id` filtering returns the right subset.
  e2e — create a second board, add a card there, confirm the first board is unaffected across reload.
- **Acceptance:** the multi-board demo works; existing data preserved under the default board.

## V8 · Board authorization ✅ Built

> **Built** (ADR 0013). One sync **principal resolver** (`app/authz.py`): a cookie session → `User`,
> else a valid `API_TOKENS` bearer → a **SERVICE** sentinel, else `401`. A single `authorize_board`
> gates every board-scoped route (cards + epics list/get/create/patch/delete/move, board detail/
> rename/delete) — owner-only, else `403`; lists are owner-scoped. `/api/v1` is now **auth-required**
> (V4's `require_token` write-guard removed). Two forks resolved with the maintainer: **claim-on-login**
> (`UserManager.on_after_login` adopts unclaimed boards → the first human rescues the migrated default
> board), and **`API_TOKENS` as a transitional SERVICE bypass** so the MCP server keeps working until
> V9 (retired then). Also: a story's epic must be on the **same board** (422). Test-harness reworked:
> integration tests run as a board-owning session (`login_as` factory + `service_client`); e2e uses an
> **e2e-only** `POST /auth/test-login` seam (`E2E_AUTH_BYPASS`, never in prod) for a real session.

- **Build:** a **board-authorization** dependency — the resolved principal must own the target board,
  else `403`. Applied to every board-scoped read/write (cards, epics, board detail); list endpoints
  return only the principal's boards/cards. This makes `/api/v1` **auth-required** (a deliberate,
  documented contract change — all our clients move together, so it stays under `/api/v1`).
- **Tests:** integration — owner allowed; non-owner `403` on read/write/move/delete; list endpoints
  omit others' data; unauthenticated → 401. e2e — a second logged-in user cannot see the first's board.
- **Acceptance:** the isolation demo (A can't touch B) holds across API + UI.

## V9 · Agent tokens ✅ Built

> **Built** (ADR 0014). `personal_access_token` table (migration `0006`); `/api/v1/tokens` CRUD
> (create → secret revealed **once**; list metadata; revoke = delete). Secrets **hashed at rest** —
> HMAC-SHA256 peppered with `AUTH_SECRET`, indexed for an O(1) lookup (not bcrypt: a 256-bit random
> token needs no slow hashing and must stay look-up-able). A PAT is the **third branch of the one
> principal resolver** (`app/authz.py`): a valid PAT bearer → its owning `User`, then the *same*
> `authorize_board` check humans use — so an agent is owner-gated identically to its owner. Fully
> **sync** (ADR 0008); only humans touch the async engine. Token management is per-user
> (`require_user`; the SERVICE bypass gets 403). SPA gains a top-bar **Tokens** view (create /
> reveal-once / revoke). **Supersedes `API_TOKENS` as the agent mechanism** (ADR 0010), but the
> transitional SERVICE bypass is **kept until V10** rewires MCP onto PATs and removes it.

- **Build:** `personal_access_token` table (`user_id`, `name`, `token_hash`, `created_at`,
  `last_used_at`, nullable `expires_at`); `/api/v1/tokens` (create → returns the secret **once**;
  list metadata; revoke). A **sync bearer dependency** hashes the presented token, looks it up,
  updates `last_used_at`, and resolves to its owning `User` — feeding the same principal + board
  authz as human sessions. **Retires V4's `API_TOKENS` env list** (ADR 0010 → superseded). SPA:
  a **Tokens page** (create/name/reveal-once/revoke).
- **Tests:** integration — create→use→revoke lifecycle; token hashed at rest (never returned again);
  bad/expired/revoked → 401; a token only reaches its owner's boards (writes honour board authz).
  e2e — create a token in the UI, see it once, revoke it.
- **Acceptance:** the token 201→revoke→401 demo works; secrets stored hashed. **Prod:** drop the
  `API_TOKENS` Fly secret once agents use PATs.

## V10 · MCP board-scoping ✅ Built

> **Built** (ADR 0015). **Part A (feature):** MCP tools gained a **board target** — a per-call
> `board_id` on `list_cards`/`list_epics`/`create_card`/`create_epic` (card-id-addressed tools need
> none), a `KANBAN_BOARD_ID` config default, and `list_boards`/`create_board` discovery tools (R2.2).
> The **no-board fallback is kept** (list = all your boards; create = earliest) with `list_boards` as
> the obvious entry point. Errors surface `403` (wrong board) / `401` (bad token) with agent-facing
> hints. **Part B (cleanup):** the transitional `API_TOKENS` **SERVICE bypass is removed** — every
> principal is now a real `User` (cookie session or PAT), ADR 0010 fully retired. The MCP server
> stays a thin `httpx` adapter, so this is client-side + a backend deletion. Two forks resolved with
> the maintainer: **keep the fallback** and **per-user test cleanup** (no admin/`is_superuser`
> capability). **Ops:** drop the `API_TOKENS` Fly secret.

- **Build:** MCP tools gain a **board target** (a `KANBAN_BOARD_ID` config default and/or a per-call
  `board_id`) and send a user **PAT** (`KANBAN_TOKEN`, now a real hashed PAT). `list_cards`/writes
  operate within that board; `create_board`/`list_boards` tools added so an agent can manage boards
  (R2.2). `.mcp.json.example` + README updated (board + token). Errors surface `403` (wrong board) /
  `401` (bad token) clearly. Backend: remove the `API_TOKENS` SERVICE bypass (`app/authz.py` +
  `app/auth.py`); rework the SERVICE-dependent tests to cookie/PAT + per-user cleanup.
- **Tests:** unit — each tool sends the board scope + bearer token (mocked httpx); error mapping for
  401/403; smoke — the tool list includes the board tools. Backend — unauthenticated `401`, owner
  `200`, non-owner `403` with cookie + PAT only (no SERVICE). e2e — cleanup works per-user.
- **Acceptance:** Claude, via MCP, creates/moves cards on a chosen board and is blocked from another
  user's board (verified live with a PAT). **Milestone demo:** dogfood — an agent keeps this repo's
  own board current.

---

## Notes / decisions folded in

- **Two engines, one DB, one `Base`** (D6, spike-validated): async engine for fastapi-users' human
  login only; the sync engine keeps serving all board/card/epic CRUD **and** the PAT lookup.
- **`/api/v1` becomes auth-required** (V8): a real contract change, but every client (SPA, e2e, MCP)
  moves in lockstep and we own them all, so no `/api/v2` — it stays versioned in place (R6.2).
- **CI:** V6 adds the async-auth deps to the backend job (no new job); the frontend gains landing +
  auth-routing + tokens pages (existing jobs cover them); V10 touches the existing `mcp` job.
- **New ADRs** to write alongside the build: **evolve ADR 0007** (no-auth → cookie sessions + board
  authz) and **ADR 0006** (single board → multi-board with ownership); **supersede ADR 0010** (env
  `API_TOKENS` → user-owned hashed PATs).
- **Deferred to a later milestone:** roles (R3.2), board sharing (R3.3), fine-grained token scoping
  (R4.2), audit trail (R5.1), soft-delete (R5.2).
