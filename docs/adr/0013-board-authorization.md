# ADR 0013 — Board authorization (`/api/v1` becomes auth-required)

- **Status:** Accepted
- **Date:** 2026-07-09
- **Context source:** Milestone 3 (Accounts, Boards & Agent Access), requirements R3.1/R3.4,
  decisions D3/D5; Shape A part **A5**; BREADBOARD place **S5** ("principal resolver" +
  "board-authorization dependency"). Realises the "one authorization layer" of D3 and the contract
  change flagged in SLICES § V8. Builds directly on ADR 0011 (cookie sessions) and ADR 0012
  (multi-board with ownership); evolves ADR 0007's no-auth stance further and supersedes the
  *default* behaviour of ADR 0010 for board routes. Delivered as slice **V8**.

## Context

V6 added a human `User` + revocable cookie session (ADR 0011); V7 made `board` first-class with a
(nullable) `owner_id` but **enforced nothing** — any request could read/write any board, and the
board list was unscoped (ADR 0012). V8 is where ownership starts to *mean* something: a board's
owner, and only its owner, may see or change it (R3.1/R3.4), enforced **server-side** so no client
can bypass it. This necessarily makes the whole `/api/v1` surface authorization-required — a
deliberate, documented contract change from V4, where reads were open and writes were open unless
`API_TOKENS` was set (ADR 0010).

Two forks had to be resolved before building (confirmed with the maintainer):

1. **The unclaimed default board.** V7's migration left it `owner_id NULL`, so an owner-only check
   would hide it from everyone and strand the migrated production data.
2. **Agents during the V8→V9 window.** V8's principal is the human cookie session only; per-user
   agent PATs are V9. But making `/api/v1` auth-required would break the MCP server, which
   authenticates with the shared `API_TOKENS` bearer (not tied to a user, so it can't pass an owner
   check).

## Decision

- **One principal, one check (D3).** A single sync **principal resolver** (`app/authz.py:get_principal`)
  resolves each request to a principal: a valid `kanbanauth` cookie session → the `User` (via
  fastapi-users' `current_optional_user`, on the async engine); failing that, a valid `API_TOKENS`
  bearer → a **SERVICE** sentinel. No principal → **401**. A single `authorize_board(db, principal,
  board_id)` then allows iff the principal owns the board, else **403** (**404** if the board is
  missing). The sync board routes depend on the async `current_optional_user` — FastAPI resolves the
  async sub-dependency for a sync endpoint (proven in V7), so ADR 0008's sync board engine is intact.
- **Applied to every board-scoped route.** Cards and epics (list/get/create/patch/delete/move) and
  board detail/rename/delete all resolve a principal and authorize the target board (the card's/
  epic's `board_id`, or the path/`board_id` param). **List endpoints are owner-scoped**: `GET
  /boards`, `GET /cards`, `GET /epics` return only the caller's rows; a `board_id` naming a board you
  don't own is a `403` (not a silently-empty list).
- **`/api/v1` is now auth-required (R3.4).** This replaces V4's `require_token` write-guard entirely
  — the "open when `API_TOKENS` unset" default is gone for board routes. It stays under `/api/v1`
  (no `/api/v2`): we own every client (SPA, e2e, MCP) and move them together (R6.2).
- **Claim-on-login rescues the default board (fork 1).** `UserManager.on_after_login` adopts every
  unclaimed board (`owner_id IS NULL`) for the logging-in user. The first human to log in claims the
  migrated default board (and its data); it is idempotent, so it never re-assigns an owned board.
  Chosen over an explicit "claim" action (less to build this slice) and over leaving boards orphaned
  (which would strand prod data).
- **`API_TOKENS` is a transitional SERVICE bypass (fork 2).** A valid `API_TOKENS` bearer resolves
  to SERVICE, which **bypasses** the owner check (full access to all boards). This keeps the MCP
  server working during V8→V9 without silently breaking it. It is not a regression: that shared
  credential already granted full write access. **V9 retires `API_TOKENS`** in favour of per-user
  hashed PATs that resolve to a real `User` (ADR 0010 → superseded).
- **One board owns its epics and stories.** `_validate_epic` now requires a story's `epic_id` to
  reference an epic **on the same board** (422 otherwise) — no cross-board epic links via the raw
  API, closing the gap ADR 0012 left to the SPA's board-scoped selector.

## Consequences

- **Positive:** ownership is enforced server-side across API + UI (the isolation demo — user A
  cannot see or touch user B's board — holds end to end); the migrated prod data is recovered
  automatically on first login; the sync board engine and flat router style are unchanged (ADR 0008);
  the MCP path keeps working via the SERVICE bypass until V9.
- **Test-harness rework.** Almost every backend integration test hit `/api/v1` unauthenticated;
  they now run as a board-owning session user (the happy-path files shadow their `client` fixture
  with `logged_in_client`, which owns the default board via claim-on-login), with a `login_as`
  factory for the second user in the 403/scoping tests and a `service_client` for the SERVICE
  bypass. e2e can no longer fake auth with a `page.route` stub of `/users/me` — it needs a real
  cookie — so an **e2e-only** `POST /auth/test-login` seam (gated by `E2E_AUTH_BYPASS`, never mounted
  in prod) mints a real session; specs open a fresh owned board per test.
- **Negative / deferred:** the SERVICE bypass is a shared, unscoped credential (mitigated: transitional,
  retired in V9); the *first* human to log in adopts **all** unclaimed boards (acceptable for a
  single-tenant/dogfooding deployment; multi-tenant claiming is out of scope); roles (R3.2), board
  sharing (R3.3), fine-grained token scope (R4.2), and an audit trail (R5.1) remain Later.
