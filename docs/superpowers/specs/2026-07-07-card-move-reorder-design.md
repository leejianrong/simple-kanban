# Design — Card move & reorder (R2)

- **Date:** 2026-07-07
- **Status:** Approved (brainstorming)
- **Sources:** `docs/SHAPING.md` (Shape A), `docs/BREADBOARD.md` §5–§6, `docs/adr/0006-data-model-and-domain-decisions.md`, `docs/adr/0007-no-auth-concurrency-and-realtime.md`

## Goal

Let a user move a card between columns and reorder it within a column, with changes
persisting across reloads. This implements requirement **R2** (Core) from `SHAPING.md`:

- **R2.1** Drag a card from one column to another; its column updates. *(Core)*
- **R2.2** Reorder a card within a column; its position updates. *(Must)*
- **R2.3** Moves/reorders persist and survive reload. *(Must)*

Slice 1 already ships `GET`/`POST /api/cards` and a board that renders three columns
and creates cards. This slice adds the move capability on top.

## Scope

**In scope**
- Backend `POST /api/cards/{id}/move { column, position? }` endpoint.
- `renumber_column()` ordering helper and the transactional move algorithm.
- `CardMove` Pydantic schema.
- Frontend drag-and-drop (between and within columns) wired to the endpoint.
- Backend pytest coverage for the move endpoint.

**Out of scope**
- `PATCH`/`DELETE /api/cards/{id}` (field edit / delete) — separate slices (R1.3/R1.4).
- Playwright frontend smoke harness (R8.2) — deferred (see Decision 2).
- Optimistic UI, real-time sync, concurrency reconciliation — excluded by ADR 0007
  (last-write-wins; refetch after mutation).

## Key architectural rule

Both outcomes — drag *between* columns (R2.1) and drag *within* a column (R2.2) —
funnel through the single endpoint `POST /api/cards/{id}/move`. After a successful
move the client refetches `GET /api/cards`; the server's order is authoritative. No
optimistic UI (Shape A, ADR 0007). On error the client refetches and reverts to the
last known server order, so the board never displays an order the server did not confirm.

## Backend design

### `schemas.py` — add `CardMove`
- `column: ColumnEnum` (required) — reuses the existing `ColumnEnum` (`todo`/`in_progress`/`done`).
- `position: int | None = None` — optional; if given must be `>= 0`; if omitted the card
  appends to the end of the target column. Non-integer values → `422`.

### `ordering.py` — add `renumber_column(db, column)`
- Load the column's cards ordered by `position` and reassign `position = 0..n`
  contiguously. Used to close the gap in the **source** column after a cross-column move.
  Complements the existing `next_position()` used on create (which stays).

### `routers/cards.py` — add `POST /api/cards/{id}/move`
Algorithm, in one transaction:
1. Load the card by `id`; return `404` if it does not exist.
2. Remember the source column. Build the **target** column's cards ordered by `position`,
   *excluding the moved card*.
3. Compute the target index: clamp `position` to `[0, len(that list)]`; `None` ⇒ append
   at the end (index = `len`).
4. Insert the moved card into that ordered list at the target index, then assign
   `position = 0..n` across the whole list (so the moved card takes the chosen slot and its
   new siblings stay contiguous). Set `card.column` to the target column.
5. If the source column differs from the target, call `renumber_column(source)` to close the
   gap the card left behind.
6. `updated_at` bumps automatically via the model's existing `onupdate=func.now()`.
7. Return `200` with `CardRead`.

### Validation & errors
| Condition | Result |
|-----------|--------|
| `column` not in {todo, in_progress, done} | `422` |
| `position` present but not an integer / `< 0` | `422` |
| card `id` does not exist | `404` |
| valid move (incl. no-op, empty target, append) | `200 CardRead` |

Error shape is FastAPI's standard `{ "detail": ... }` (R4.4).

## Frontend design

### `lib/api.ts`
Add `moveCard(id, { column, position? }): Promise<Card>` — same typed-fetch,
throw-on-non-2xx pattern as `createCard`.

### `lib/board.svelte.ts`
Add `moveCard()` wrapper that calls the API then `refetch()` — mirrors the existing
`addCard()`; never mutates board state optimistically.

### Drag & drop
- Use `svelte-dnd-action` on `Column.svelte`: each column is a drop zone; cards
  (currently rendered inline in `Column.svelte`) are draggable. No separate `Card.svelte`
  component is introduced — the existing inline card markup is wrapped in the dnd action.
- On drop, compute `{ column: <target column>, position: <target index> }` from the drop
  zone and insertion index, call `moveCard`, then refetch.
- Esc / drop-outside cancels the drag with no API call.
- Optional: skip the API call when the card lands in its original slot (no-op); a redundant
  `/move` is also safe because renumber yields the identical order.

## Testing

### Backend (pytest — harness already exists)
The suite runs against an ephemeral Postgres via testcontainers (`tests/conftest.py`,
requires Docker). Add cases covering:
- Move a card to a different column (source and target both re-sequence; `column` changes;
  `ticket_number`, `story_points`, `assignee` unchanged).
- Reorder within a single column (only that column re-sequences).
- Drop into an empty column (lands at position 0).
- Omitted `position` appends to the end of the target.
- Source-column gap closes after a cross-column move (remaining positions are `0..n`).
- `position` beyond range is clamped to the end.
- Unknown `id` → `404`.
- Bad `column` → `422`.

Backend logic is developed test-first (TDD).

### Drag UI
Verified manually by driving the actual board (`/run` + `/verify`) — load, create, drag
between columns, drag within a column, reload to confirm persistence. Interaction-heavy UI
is not covered by an automated test in this slice (see Decision 2).

## Decisions on open items

1. **`svelte-dnd-action` compatibility.** The repo is on Vite 8 / Svelte 5.x and the library
   is not yet installed. The **first implementation step is a spike** to confirm it builds and
   drags under this exact setup. If it does not work cleanly, fall back to **native HTML5 drag
   events** — same endpoint, same UX, no new dependency. (SHAPING lists this fallback as the
   resolution for unknown #5.)
2. **Frontend smoke test (R8.2) deferred.** No Playwright harness exists in this repo yet, and
   standing one up is a separate sizable task. This slice relies on thorough backend pytest
   coverage plus manual UI verification. The Playwright happy-path smoke (load → create → move)
   is tracked as follow-up work, not part of this slice.

## Requirement coverage

| Requirement | Covered by |
|-------------|-----------|
| R2.1 Drag between columns | move endpoint + dnd drop onto another column |
| R2.2 Reorder within a column | move endpoint + dnd reorder within a column |
| R2.3 Moves persist | DB write + post-move refetch; verified by reload |
| R4.3 Dedicated move endpoint | `POST /api/cards/{id}/move` |
| R4.4 Standard JSON validation errors | `422`/`404` via FastAPI/Pydantic |
| R8.1 Backend tests for move/reorder | pytest cases above |
