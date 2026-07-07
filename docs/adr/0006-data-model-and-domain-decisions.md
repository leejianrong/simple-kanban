# ADR 0006 — Data model & domain decisions (MVP)

- **Status:** Accepted
- **Date:** 2026-07-07

## Context

The MVP needs a concrete, minimal domain model. REQS.md lists cards with title, description, story
points, assignee, and a Jira-like number, plus Todo/In Progress/Done columns and drag-to-move.
"etc." and several details were left open; we resolve them here, biased toward the simplest thing
suited to the MVP scope.

## Decision

- **Single global board.** The board is implicit, not a stored entity. Multi-board is out of scope.
- **Columns are a fixed enum** `todo | in_progress | done`, stored as a `varchar` + CHECK
  constraint with app-level (Pydantic) validation — not a native PostgreSQL enum, so future values
  need no `ALTER TYPE` migration (see ADR 0008). No custom/renamable columns, no WIP limits.
- **Card fields:** `id`, `ticket_number`, `title` (required), `description` (optional plain text),
  `column`, `position`, `story_points`, `assignee`, `created_at`, `updated_at`. No priority,
  labels, due dates, comments, or attachments in the MVP.
- **Ticket number:** `KAN-<n>` from a global monotonic Postgres sequence; assigned once at
  creation, immutable, never reused. Prefix `KAN` is hardcoded.
- **Story points:** nullable; restricted to the Fibonacci set {1, 2, 3, 5, 8, 13}; null =
  unestimated.
- **Assignee:** nullable free-text string (there is no user account — see ADR 0007 no-auth).
- **Ordering:** cards keep a `position` within their column so drag-to-reorder is supported, not
  just drag-between-columns.
- **Move:** exposed as a dedicated `POST /api/cards/{id}/move` — required target `column`, optional
  `position` (if omitted, the card is appended to the end of the target column). Distinct from
  `PATCH` field edits — clearer semantics for the UI and future agent tools.
- **Lifecycle:** cards can be edited and hard-deleted. No archive, no soft-delete, no move history.

## Consequences

- **Positive:** Minimal schema, one table, trivial validation. Fixed columns and a global sequence
  are simple and bug-resistant. `position` gives credible kanban UX cheaply.
- **Negative:** Adding features later (custom columns, labels, multi-board) will require new
  migrations and possibly a `Column`/`Board` table. Accepted — these are explicit non-goals now.
- **Note on `story_points` as an enum:** if teams later want arbitrary estimates, relax the
  validation — no schema change (it's stored as a nullable int).
