---
shaping: true
---

# Milestone 3 — Breadboard (Accounts, Boards & Agent Access)

Concrete affordances + wiring for **Shape A** (see [SHAPING.md](SHAPING.md)). Places are where
work happens; affordances are what exists there; wiring shows the calls. Ground truth is the
affordance tables — the diagram renders them.

## Places

| Place | What it is |
|-------|-----------|
| **S1 · Landing** | Logged-out front door (`Landing.svelte`) — hero + "Sign in with GitHub". No board data. |
| **S2 · Auth** | fastapi-users on an **async** engine: GitHub OAuth router, users router, cookie session (revocable). |
| **S3 · App shell** | Logged-in SPA: top bar with user + logout + **board switcher**; the existing board view, now board-scoped. |
| **S4 · Tokens page** | Self-serve agent **personal access token** management (create / list / reveal-once / revoke). |
| **S5 · REST API `/api/v1`** | Boards CRUD + the existing cards/epics, now **auth-required and board-scoped**. Sync engine. |
| **S6 · MCP server** | The V5 stdio server, now **board-scoped** and authenticating with a user PAT. |

## UI affordances

| Affordance | Place | Wires out |
|-----------|-------|-----------|
| Hero + **Sign in with GitHub** button | S1 | `GET /auth/github/authorize` (→ GitHub → callback) |
| Top bar: user name/avatar + **Log out** | S3 | `GET /users/me`; `POST /auth/logout` |
| **Board switcher** (list + select) + **New board** / rename / delete | S3 | `GET/POST/PATCH/DELETE /api/v1/boards` |
| Board view (columns, cards, epics — existing) scoped to the selected board | S3 | `GET /api/v1/cards?board_id=…`, `…/epics?board_id=…` |
| **Tokens page**: token list, **New token** (name → reveal once), **Revoke** | S4 | `GET/POST/DELETE /api/v1/tokens` |

## Non-UI affordances

| Affordance | Place | Wires out |
|-----------|-------|-----------|
| `User` + `OAuthAccount` + `access_token` tables (async store, fastapi-users) | S2 | async engine |
| GitHub OAuth client + `get_oauth_router`; `CookieTransport` + `DatabaseStrategy` | S2 | writes `User`/`OAuthAccount`; sets httpOnly cookie |
| `board` table (`owner_id`→user); `card.board_id` / `epic.board_id` FKs | S5 | sync engine |
| `personal_access_token` table (`user_id`, name, `token_hash`, created/last_used/expiry) | S5 | sync engine |
| **Principal resolver**: cookie-session (human) *or* bearer PAT (agent) → `User` | S5 | reads session / hashes+looks-up token |
| **Board-authorization** dependency: principal must own the board (else 403) | S5 | on every board-scoped route |
| Alembic migration: create auth + board + token tables; backfill a default board + attach existing cards/epics | S5 | one shared `Base` metadata |
| MCP tools take a board target + send a PAT | S6 | `/api/v1/*` with `Authorization: Bearer <PAT>` |

## Wiring

```
S1 Landing ──"Sign in with GitHub"──▶ S2 /auth/github/authorize ──▶ GitHub ──▶ callback
                                          └─ creates/links User, sets httpOnly cookie ─┐
                                                                                        ▼
S3 App shell ◀────────── GET /users/me (who am I?) ─────────────────────────── S2/S5 principal
   board switcher ──▶ S5 /api/v1/boards (owned by me)
   board view    ──▶ S5 /api/v1/cards?board_id  ──▶ [principal resolver] ──▶ [board authz: own it?] ──▶ data
S4 Tokens page  ──▶ S5 /api/v1/tokens (create → reveal once / revoke)

S6 MCP ──(Bearer PAT, board target)──▶ S5  ──▶ [principal = token's user] ──▶ [board authz] ──▶ writes
```

## Coverage check (requirement → affordance)

| Requirement | Where |
|-------------|-------|
| R1.1 GitHub login · R1.3 session/logout · R1.4 User | S2 |
| R1.2 modular providers | S2 (fastapi-users backend/OAuth-client config) |
| R1.5 landing page | S1 |
| R2.1 human board CRUD · R2.3 card/epic ∈ board | S3 + S5 |
| R2.2 agents manage boards | S5 (boards API) + S6 |
| R3.1 board owner · R3.4 server-enforced access | S5 (authz dep) |
| R4.1 self-serve tokens · R4.3 attributable + metadata · R7.1 hashed | S4 + S5 |
| R4.4 MCP token + board scope | S6 |
| R6.1 migration · R6.2 versioned/back-compat | S5 (migration; `/api/v1` retained) |
| R7.2 single-origin | unchanged (cookies same-origin; no CORS) |

Deferred (not in M3): R3.2 roles, R3.3 sharing, R4.2 fine-grained token scope, R5.1 audit, R5.2 soft-delete.
