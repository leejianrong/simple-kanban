# ADR 0012 — Multi-board with ownership

- **Status:** Accepted
- **Date:** 2026-07-08
- **Context source:** Milestone 3 (Accounts, Boards & Agent Access), requirements R2.1–R2.4, R3.1,
  R6.1; evolves the **single-board** stance of ADR 0006. Delivered as slice **V7**.

## Context

ADR 0006 deliberately made the board **implicit** — "single global board, not a stored entity;
multi-board is out of scope" — as an MVP simplification, while noting that multi-board would later
need a `Board` table + migration. Milestone 3 needs exactly that: humans (and agents) create and
switch between multiple boards (R2.1/R2.2), every card and epic belongs to exactly one board
(R2.3), and a board has an owner so V8 can enforce access (R3.1). Existing production data must
migrate with no loss (R6.1). Ticket numbering is resolved separately (D4): `KAN-`/`EPIC-` stay
**global** across boards for M3 — no per-board prefixes.

## Decision

- **`board` is now a first-class table** (`id`, `name`, `owner_id`, timestamps). The board is no
  longer implicit. `card` and `epic` each gain a **NOT NULL `board_id`** FK → `board`
  (`ON DELETE CASCADE`) — every card/epic belongs to exactly one board (R2.3), and deleting a board
  removes its cards + epics.
- **Ownership is nullable.** `board.owner_id` → `user.id` (`ON DELETE SET NULL`: deleting a user
  *unclaims* their boards rather than cascading the boards + all their cards away). A board created
  through the API is owned by the **session user** when one is present, else unowned — captured from
  the session, never the request body.
- **Migration backfills a single unclaimed default board** (`owner_id` NULL) and attaches every
  existing card + epic to it (R6.1) — columns added nullable, backfilled, then set NOT NULL. The
  "unclaimed default board" choice avoids depending on a user existing at migration time (login only
  just shipped; prod may have data but zero accounts). How the default board gets claimed/shown is a
  V8 concern.
- **Positions are per (board, column).** `next_position`/`renumber_column` and the move endpoint are
  scoped by `board_id`, so ordering and drag-reorder never cross boards.
- **`board_id` is optional on card/epic create**, defaulting to the earliest board. This keeps
  pre-board clients working unchanged (the MCP server, older tests, any script) — API-first
  back-compat (R6.2). The SPA always sends it to scope the active board.
- **No authorization yet.** V7 adds boards + ownership data but **not** enforcement: any request may
  list/read/write any board, and the board list is unscoped. Server-enforced owner-only access
  (list scoping + `403`) is **V8** — ownership is captured now so V8 has real data to enforce.
- **Ticketing stays global (D4).** `card_ticket_seq`/`epic_ticket_seq` are untouched; `KAN-`/`EPIC-`
  numbers remain unique across all boards. Per-board prefixes are a later concern (R2.4).

## Consequences

- **Positive:** multi-board with owners is in place for V8's authorization and V9's per-user tokens;
  existing data is preserved under the default board; the sync board engine + flat router style are
  unchanged (ADR 0008). Back-compat means the MCP server keeps working (it lands on the default
  board until V10 adds board targeting).
- **Evolves ADR 0006.** The "single global board" simplification is superseded; the note there
  ("multi-board will require a `Board` table") is now realised. Columns, ticketing, story points,
  and the move/edit split are otherwise unchanged.
- **Negative / deferred:** cascade delete means removing a board is destructive (a UI confirm
  guards it); an unclaimed default board is visible to everyone until V8 defines claiming + access;
  cross-board epic links aren't prevented server-side in V7 (the SPA only offers same-board epics in
  the selector). Roles, sharing, and per-board ticket prefixes remain Later.
