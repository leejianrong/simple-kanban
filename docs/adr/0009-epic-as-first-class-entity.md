# ADR 0009 — Epic as a first-class entity

- **Status:** Accepted
- **Date:** 2026-07-08
- **Context source:** Milestone 2 (Agent-Driven Task Tracking), requirement R1.1; refines the
  epic/story model first sketched as `kind + parent_id` on `card` (see `docs/milestone-2/`).

## Context

Milestone 2 R1.1 requires the board to represent **epics** and **stories**, where a story can
belong to a parent epic. The first cut modeled this as a `kind` (`epic`|`story`) column plus a
`parent_id` self-FK on the single `card` table — i.e. an epic was just a card.

Reviewing that against how epics actually behave (informed by Jira's model) surfaced that an epic is
**not** the same shape as a board card:

- an epic has **no assignee and no story points** — it is a large initiative, owned by no single
  person and too big to estimate; its child stories carry the assignees and points;
- an epic is **not placed on the kanban board** — it has no column and no drag position; the board
  tracks the flow of *stories*;
- an epic wants its **own identifier space** (`EPIC-1`, `EPIC-2`…), distinct from card `KAN-n`;
- epics are **created and read in a separate UI surface**, not inline on the board.

Forcing those differences onto the `card` table (nullable `column`/`position`, a conditional
`EPIC-`/`KAN-` ticket trigger, and validation rejecting card-only fields when `kind='epic'`) is more
complex than modeling the epic as what it now is: a separate entity.

## Decision

- **Epic is its own table** (`epic`), not a `card` row. Fields: `id`, `ticket_number`, `name`
  (required), `description` (optional), `created_at`, `updated_at`. **No** `column`, `position`,
  `assignee`, or `story_points`.
- **Separate ticket sequence.** Epics get `EPIC-<n>` from their own Postgres `epic_ticket_seq`
  (server-default `'EPIC-' || nextval(...)`), independent of the card `card_ticket_seq` — so `KAN-1`
  and `EPIC-1` coexist. Same atomic-at-INSERT, immutable, never-reused mechanism as cards (ADR 0006).
- **Stories link to an epic** via a nullable `card.epic_id` FK → `epic.id`, **`ON DELETE SET NULL`**:
  deleting an epic **detaches** its stories (does not block, does not cascade), consistent with the
  hard-delete model (ADR 0006/0007). A story has zero-or-one epic.
- **API:** a new `/api/epics` resource (list/create/get/patch/delete) alongside `/api/cards`
  (API-first, ADR 0005). `card.epic_id` is accepted on create and PATCH; that it references an
  existing epic is validated in the router (422 otherwise). `GET /api/cards` continues to return the
  board's stories.
- **UI:** the board shows stories only; each story renders its epic's name as a tag. Epics are
  created and read in a separate **Epics view** (a top-bar `Board | Epics` toggle — no client-side
  router), which also rolls up each epic's child stories.

## Consequences

- **Positive:** each entity is exactly the shape it needs; no nullable board columns on epics, no
  conditional ticket trigger, simpler validation (a cross-table existence check). The clean split
  maps directly to the separate UI surface and to future agent tools (`create_epic` vs `create_card`).
- **Supersedes part of ADR 0006.** That ADR's "single global board, **one table, no other
  entities**" stance was an explicit MVP simplification; ADR 0006 itself anticipated that later
  features "will require new migrations and possibly a `Column`/`Board` table." Introducing `epic` is
  that evolution. The card table and all its mechanisms are otherwise unchanged.
- **Negative / deferred:** epics carry no dates yet (start/due) — deferred until a roadmap/timeline
  view exists to use them (nullable columns, additive later). Epic↔story is one level deep (epics
  don't nest), matching R1.1; deeper hierarchies are out of scope.
