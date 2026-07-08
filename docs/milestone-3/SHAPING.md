---
shaping: true
---

# Milestone 3 — Shaping (Accounts, Boards & Agent Access)

Working document. See [FRAME.md](FRAME.md) for the why. Status legend:
**Core goal · Must-have · Nice-to-have · Undecided · Later** (real, but a future milestone).
🟡 marks requirements proposed during shaping (not in the original ask) or otherwise changed.

Several of these were parked as **"Later"** in Milestone 2's SHAPING.md (R2 multi-board, R3.2/3.3
human auth + authz, R3.4 scoped tokens, R5 audit/soft-delete) — this milestone picks them up.

---

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| **R0** | **Humans sign in; humans and agents work on boards they're authorized to; users manage agent access — with a record of who changed what** | Core goal |
| **R1** | **Human authentication** | |
| R1.1 | Users log in via GitHub OAuth | Must-have |
| R1.2 | Auth providers are modular/pluggable — add Google / a user-mgmt library (fastapi-users) later without reworking the app | Must-have |
| R1.3 | 🟡 The SPA stays signed in across reloads (session handling) and can log out | Must-have |
| R1.4 | 🟡 A first-class **User** identity exists (id, provider, profile) that other entities reference | Must-have |
| R1.5 | 🟡 Logged-out visitors see a simple, attractive **landing page** with a "Sign in with GitHub" CTA (no public board) | 🟡 Must-have |
| **R2** | **Boards (multi-board)** | |
| R2.1 | Humans can create / rename / delete boards | Must-have |
| R2.2 | Agents can create / manage boards too (via API + MCP) | Must-have |
| R2.3 | 🟡 Every card and epic belongs to exactly one board | Must-have |
| R2.4 | 🟡 Ticket numbers stay unique and meaningful across boards — **keep global `KAN-`/`EPIC-` sequences** for M3; per-board prefixes deferred | 🟡 Must-have (resolved) |
| **R3** | **Authorization & sharing** | |
| R3.1 | 🟡 A board has an owner; only authorized users/agents can see or change it | Must-have |
| R3.2 | 🟡 Roles distinguish read vs write (e.g. owner / editor / viewer) | 🟡 Later |
| R3.3 | 🟡 An owner can share a board with other users (invite / grant / revoke) | 🟡 Later |
| R3.4 | 🟡 A writer can only affect boards they're permitted to (enforced server-side) | Must-have |
| **R4** | **Agent token management** | |
| R4.1 | Users create, name, and revoke agent tokens themselves (self-serve, in the UI) | Must-have |
| R4.2 | 🟡 Tokens are scoped — which board(s), and read vs write | 🟡 Later |
| R4.3 | 🟡 A token acts on behalf of its owning user (attributable), with metadata (created, last-used, optional expiry) | 🟡 Must-have |
| R4.4 | 🟡 The MCP server authenticates with a user's token and targets a specific board | Must-have |
| **R5** | **Auditability & trust** | |
| R5.1 | 🟡 An audit trail records who changed what and when — human user vs which agent token | 🟡 Later |
| R5.2 | 🟡 Deletes are recoverable (soft-delete / undo) | Later |
| **R6** | **Migration & compatibility** | |
| R6.1 | 🟡 Existing board-less cards/epics migrate into a default board with an owner (no data loss) | Must-have |
| R6.2 | 🟡 API stays versioned and as back-compat as possible; MCP tools gain board scoping | Must-have |
| **R7** | **Security & non-functional** | |
| R7.1 | 🟡 Token secrets are stored hashed at rest (never plaintext); shown once on creation | Must-have |
| R7.2 | 🟡 Single-origin serving preserved; no new cross-origin/CORS surface | Must-have |
| R8 | 🟡 Ships as demo-able vertical slices behind CI, matching the established cadence (R8 carried from M2) | Must-have |

---

## Decisions log

- **D1 — Appetite: foundation-first.** In scope: human login (GitHub) + modular auth, a User
  identity, multi-board with ownership, server-enforced board access, self-serve agent tokens,
  data migration. **Deferred to a later milestone:** roles (R3.2), board sharing (R3.3),
  fine-grained token scoping (R4.2), audit trail (R5.1), soft-delete (R5.2).
- **D2 — Adopt `fastapi-users` now.** Build on its `User` + OAuth-account models and its auth-backend
  abstraction from the start (satisfies the modular R1.2 by construction; Google/email later are
  config, not rework). ⚠️ Introduces a sync/async question — see `spike-fastapi-users-sync.md`.
- **D3 — Two auth backends, one authorization layer.** Humans authenticate via an **httpOnly cookie
  session** (revocable, XSS-safe, single-origin friendly); agents via a **hashed bearer
  personal-access-token** (evolves V4). Both resolve to the same `User` principal, which the board
  access check evaluates identically. (JWT-in-localStorage rejected: XSS-exposed, hard to revoke.)
- **D4 — Ticketing stays global.** Keep the existing global `KAN-`/`EPIC-` sequences across all
  boards for M3 (no change, no migration of ids); per-board prefixes are a later concern (R2.4).
- **D5 — Agent tokens belong to a user.** A token acts *as* its owning user and inherits that
  user's board access (no separate agent identity, no per-token board/scope in M3). Changes made
  via a token are still attributable to (user + token name) for a future audit trail (R5.1).

## Open questions (remaining)

1. ✅ **Sync/async for fastapi-users — RESOLVED** by `spike-fastapi-users-sync.md`. Run **two
   engines against one DB**: keep the sync engine for board CRUD + agent-PAT lookups; add an async
   engine used only by fastapi-users' human login. One shared `Base` → one Alembic pipeline. See D6.
2. ✅ **Logged-out view — RESOLVED.** Logged-out visitors see a **landing page** (not a public
   board, not a bare login wall): a simple, aesthetically pleasing one-screen intro with a "Sign in
   with GitHub" CTA. See R1.5 + shape part A9.

## Decisions log (cont.)

- **D6 — Auth architecture (spike-resolved).** One shared `app.db.Base` (one Alembic pipeline). A
  **sync** engine keeps serving board/epic/card CRUD **and** the agent-PAT lookup (ADR 0008 intact
  for the app). A **second async** engine serves fastapi-users' human login/session/OAuth store
  only. Humans → `CookieTransport` + `DatabaseStrategy` (revocable) + GitHub OAuth router; agents →
  our own hashed `personal_access_token` table + a sync bearer dependency (evolves V4). Both resolve
  to a `User` principal feeding one sync board-authorization check.

## Shapes

**Shape A — fastapi-users async login beside the sync app** (spike-validated, D6). No ⚠️ flags on
the foundation. Ready to breadboard into concrete affordances + slices.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **User identity + async auth DB.** fastapi-users `User`/`OAuthAccount` mixins on `app.db.Base`; new async engine + `get_async_session()`; Alembic migration creates `user`/`oauth_account` (R1.4) | |
| **A2** | **GitHub login (cookie session).** `GitHubOAuth2` + `get_oauth_router`; `CookieTransport` + `DatabaseStrategy` (`access_token` table) → revocable `httpOnly` cookie; logout deletes the row (R1.1, R1.3) | |
| **A3** | **Provider modularity.** Auth backends/OAuth clients are config; adding Google/email = register another client, no rework (R1.2) | |
| **A4** | **Boards + ownership.** `board` table (id, name, `owner_id`→user); `card.board_id`/`epic.board_id` FKs; CRUD routers; global `KAN-`/`EPIC-` kept (R2.1–R2.4, R3.1) | |
| **A5** | **Board authorization.** One sync dependency: given a principal + board, allow iff owner (server-enforced on every board-scoped read/write) (R3.4) | |
| **A6** | **Agent PATs.** `personal_access_token` table (user_id, name, `token_hash`, created/last_used/expiry); self-serve create/list/revoke API+UI; sync bearer dep hashing→lookup→`User`, replacing V4's env list (R4.1, R4.3, R7.1) | |
| **A7** | **MCP board-scoping.** MCP tools take/target a board and send a user PAT; config gains the board + token (R4.4, R6.2) | |
| **A8** | **Migration.** Backfill a default board owned by a bootstrap/first user; attach all existing cards/epics to it; keep API `/api/v1` versioned + back-compat where possible (R6.1, R6.2) | |
| **A9** | **Landing page + auth-gated routing.** SPA shows a `Landing.svelte` when logged out (hero + "Sign in with GitHub" → `/auth/github/authorize`) and the board when logged in; an auth check (`GET /users/me` / session) picks which (R1.5) | |

**Breadboarded + sliced** → see [BREADBOARD.md](BREADBOARD.md) (Places S1–S6, affordances, wiring)
and [SLICES.md](SLICES.md) (V6–V10). Shaping for M3 is complete; ready to build slice by slice.

---

## Landing page plan (R1.5 / A9)

**Intent:** the front door for logged-out visitors — simple, one screen, aesthetically pleasing,
consistent with the existing SPA palette/typography, responsive, light/dark aware.

**Chosen layout: hero + 3 feature points** (Option B), one screen, top to bottom:
1. **Top bar** — `▤ Simple Kanban` wordmark/logo.
2. **Hero** — one-line value prop ("Task tracking humans and AI agents share.") + primary
   **"Sign in with GitHub"** button (links to the fastapi-users OAuth authorize route).
3. **Feature row** — three light cards: **Boards** (organize work) · **Drag & drop** (flow) ·
   **Agents via MCP** (let AI keep the board current).
4. **Footer** — one line: open-source + GitHub repo link.
- **Mechanism:** a `Landing.svelte` component; `App.svelte` renders it when the auth check says
  logged-out, else the board. The CTA is a plain link to `/auth/github/authorize`; on return the
  cookie session is set and the app shows the board.
- **Scope guard:** static/marketing content only — no new backend, no board data. Ships in the
  login slice (it's what "logged out" looks like).

