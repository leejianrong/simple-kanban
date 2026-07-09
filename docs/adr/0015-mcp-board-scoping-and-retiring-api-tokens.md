# ADR 0015 — MCP board-scoping + retiring `API_TOKENS`

- **Status:** Accepted
- **Date:** 2026-07-09
- **Context source:** Milestone 3 (Accounts, Boards & Agent Access), requirements R2.2/R4.1;
  Shape A part **A7**; BREADBOARD place **S6** (MCP board target). Builds on ADR 0012 (multi-board),
  ADR 0013 (board authorization / one authorization layer), and ADR 0014 (agent PATs). **Fully
  supersedes ADR 0010** (`API_TOKENS`). Delivered as slice **V10** — the last slice of Milestone 3.

## Context

By V9 the backend already supports everything an agent needs to work across multiple boards: the
`/api/v1` surface is owner-scoped (ADR 0013), `GET /boards` lists the caller's boards, `GET
/cards?board_id=` and `board_id` in create payloads target one board, and a **personal access
token** (ADR 0014) authenticates as its owning user and is owner-gated exactly like a human. Two
things remained:

1. **The MCP server didn't use any of it.** Its tools sent **no** `board_id`, so `list_cards` spanned
   all the caller's boards and `create_card`/`create_epic` landed on the globally-earliest board.
   There was no way for an agent to discover boards or target a chosen one — the multi-board feature
   was invisible over MCP.
2. **The transitional `API_TOKENS` SERVICE bypass was still in place.** V8 kept it (ADR 0013) so the
   MCP server kept working during the V8→V9 window; V9 kept it one more slice (ADR 0014) so V10 could
   remove it once MCP moved onto PATs. It is an unscoped, un-attributable, shared-secret bypass of the
   entire owner check — exactly the thing PATs replace — so it should not outlive its purpose.

## Decision

**Part A — MCP board-scoping (a thin client adapter, API-first / ADR 0005; no backend change).**

- **Discovery tools:** `list_boards()` (→ id + name of the boards you own) and `create_board(name)`.
- **Per-call `board_id`** on the board-scoped tools: `list_cards`, `list_epics` (new, for parity),
  `create_card`, `create_epic`. The card-id-addressed tools (`get_card`/`update_card`/`move_card`/
  `delete_card`) take **no** `board_id` — the server authorizes via the card's own board.
- **`KANBAN_BOARD_ID` env** as the default when a call omits `board_id`.
- **No-board fallback is kept** (maintainer decision): when neither a per-call `board_id` nor
  `KANBAN_BOARD_ID` is given, the client sends no `board_id` and the API applies its existing fallback
  (list = all your boards; create = your earliest board). `list_boards` is the obvious entry point for
  an agent that wants to target explicitly.
- **Clear auth errors:** the client frames `401` as a token problem ("set `KANBAN_TOKEN` to a valid
  PAT") and `403` as a wrong-board problem ("call `list_boards`"), preserving the raw server detail.
- **A real PAT is now required.** `/api/v1` has been auth-required since V8, so `KANBAN_TOKEN` must be
  a `kanban_pat_…` (created in the Tokens UI). `.mcp.json.example` + `mcp/README.md` updated.

**Part B — retire the `API_TOKENS` SERVICE bypass.**

- **Remove the `SERVICE` sentinel and the `API_TOKENS` branch** from `app/authz.py`. `get_principal`
  is now cookie-session-**or**-PAT-**or**-`401`; every resolved principal is a real `User`.
  `authorize_board` / `visible_board_ids` / `require_user` simplify accordingly (`require_user`
  becomes a self-documenting alias of `get_principal`, since there is no non-user principal left to
  reject).
- **Delete `app/auth.py`'s `API_TOKENS` reading** (`configured_tokens`); keep only the HTTP
  `bearer_scheme` the PAT branch needs.
- **Ops:** drop the `API_TOKENS` Fly secret. No maintainer impact — the maintainer is already on a PAT.

**Test harness (the practical cost of Part B).** Removing the unscoped bypass removes the one way tests
acted across users, so cross-user cleanup becomes **per-user** (maintainer decision — no admin/
`is_superuser` capability, which isn't a product requirement):

- Backend: `test_auth.py` collapses to the unauthenticated-`401` contract (the SERVICE model is gone;
  PAT owner-gating is covered by `test_tokens.py`/`test_authz.py`). The `service_client` fixture and
  the default-board-via-SERVICE observation are replaced (the latter by a direct DB check).
- e2e: the cleanup helpers act **as each owning user** via the existing `E2E_AUTH_BYPASS` test-login
  seam instead of a SERVICE bearer; `API_TOKENS` is dropped from the Playwright `webServer` env
  (`E2E_AUTH_BYPASS` stays).

## Consequences

- **Positive:** an agent can now discover boards and target any board it owns at call time — switching
  boards with no restart — while access stays bounded to the PAT owner's boards (`403` otherwise).
  There is exactly **one** kind of principal (a `User`) and **one** authorization path, so the model
  is simpler and there is no longer any shared-secret, un-attributable bypass of ownership. ADR 0010 is
  fully retired.
- **Neutral:** the MCP server remains a thin `httpx` adapter over `/api/v1` — the feature is entirely
  client-side plus a documentation/ops change; the backend diff is deletion.
- **Negative / deferred:** unchanged from ADR 0014 — no per-token board or read/write **scope**
  (R4.2), no roles (R3.2) or board **sharing** (R3.3), no full **audit trail** (R5.1). A PAT still
  reaches *all* of its owner's boards.
