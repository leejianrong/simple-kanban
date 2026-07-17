---
shaping: true
---

# Milestone 5 — Slices (Shape A)

Vertical increments of the [Shape A breadboard](BREADBOARD.md). Each
ends in **observable behaviour** and ships as its own PR behind CI, matching the M1–M4 cadence.

Numbering continues the **global V-series** (M2 = V1–V5, M3 = V6–V10; M4 was tracked directly on the
board as EPIC-3…EPIC-17 rather than V-numbers). **M5 is V11–V19.**

Order respects dependencies: card fields (V11) are the inputs dispatch and triage need; dispatch
(V12) and the handoff flag (V13) are the agent-operate core; query/saved-views (V14) + search (V15)
feed the awareness dashboard (V16); reporting (V17) rides the activity feed. Scoped tokens (V18) and
batch/templates (V19) are the *Later / Nice-to-have* tail — the milestone demos complete without them.

Every slice includes **API + MCP + CLI parity** for what it adds (R1.3) — the endpoint first, then
the MCP tool + `kan` verb, then any UI.

| Slice | What | Parts | Ends in (demo) |
|-------|------|-------|----------------|
| **V11 · Card fields** | priority, labels, due date | A1 | Set `priority`/`label`/`due` on a card via `kan`; badges/chips/overdue pill render in the UI; filter the list by them |
| **V12 · Dispatch + fleet-safe claim** | next-ready + atomic claim | A2 | Two agents call `dispatch` at once → each gets a *different* ready card, both now `in_progress` with distinct assignees; `kan next`/`kan claim` |
| **V13 · needs-human handoff** | the `needs_human` flag | A3 | An agent flags a card `needs-human` with a note via `kan`; it shows in a "needs attention" filter; clearing it + a comment lets the agent see it's resolved |
| **V14 · Query depth + saved views** | JQL-lite filters + saved views | A5 | Save a view "needs me" (filtered) and switch to it in the UI; the same filter grammar works from `kan list` |
| **V15 · Full-text search** | Postgres FTS | A6 | `kan list --q "login"` and a UI search box find matching cards, ranked |
| **V16 · Awareness dashboard** | mission control | A7 | The Dashboard shows in-flight-by-agent (+ PR/CI), a needs-attention list, the activity feed, and a table view — all read-only, refreshing |
| **V17 · Fleet reporting** | derived metrics | A8 | `GET /boards/{id}/metrics` (and `kan`) returns throughput / cycle time / aging / per-assignee; small charts in the UI |
| **V18 · Scoped tokens** *(Later)* | observer vs operator PAT | A4 | Create a read-only PAT; a write via it → `403`; a write PAT still works |
| **V19 · Batch + templates** *(Nice-to-have)* | bulk ops + templates | A9 | Seed a plan from a template in one call; batch-update several cards at once |

---

## V11 · Card fields (priority, labels, due date)

- **Build:** additive migrations — `card.priority` (`varchar` + CHECK `none/low/medium/high/urgent`,
  default `none`), `card.due_date` (`timestamptz` null); `label` table (`board_id` FK, `name`,
  `color`) + `card_label` M:N join. Schemas expose the fields; the query API gains `priority=`,
  `label=`, `due_before=`/overdue filters. MCP tools + `kan` (`create`/`update` flags, label
  create/list, list filters). UI: priority badge, colored label chips, due/overdue pill on the card
  (display + the create/edit form gains the selectors — the one place UI editing is retained).
- **Tests:** integration — set/read each field; CHECK rejects a bad priority; label is board-scoped
  (can't attach another board's label → 422); filters return the right subsets. Unit — schema
  validation. e2e — chips/badge render.
- **Acceptance:** the demo above; full suite green. Additive migration (deploys, prod-verify).

## V12 · Dispatch + fleet-safe claim

- **Build:** `POST /api/v1/boards/{id}/dispatch` — one transaction selecting the next `todo`,
  not-blocked card ordered `priority DESC, position` with `FOR UPDATE SKIP LOCKED`, setting `assignee`
  (from body/token) + moving to `in_progress`, recording activity, returning the card (or `204` when
  none ready). `GET /api/v1/boards/{id}/next` peeks without claiming. Authz `Access.WRITE`. MCP
  `dispatch`/`next` + `kan next [--claim] [--assignee] [--label] [--priority]`.
- **Tests:** integration — **concurrency test** (two sessions dispatch against a 1-card board; exactly
  one gets it, the other `204`); dispatch skips blocked cards and respects priority order; empty board
  → `204`. The `SKIP LOCKED` behaviour is the correctness crux — test it directly.
- **Acceptance:** the two-agents-no-collision demo; suite green. No migration (behaviour on existing
  columns) — still app-code, so it deploys.

## V13 · needs-human handoff

- **Build:** additive `card.needs_human` (bool default false) + `card.attention_note` (text null);
  CHECK-vocabulary migration adding `attention` + `resolved` activity actions (mirror EPIC-4's
  `restored`). `POST /cards/{id}/needs-human` (sets flag + note + activity) and `…/resolve` (clears +
  activity). Query filter `needs_human=true`. Resolution channel = the existing comments. MCP + `kan`
  verbs. UI: a needs-human badge on the card (full surfacing is V16).
- **Tests:** integration — raise → appears under `needs_human=true` + an `attention` activity row;
  resolve → cleared + `resolved` row; a comment round-trips. Auth gated.
- **Acceptance:** the flag/resolve demo; suite green. Additive migration (deploys, prod-verify).

## V14 · Query depth + saved views

- **Build:** extend the V3 query API with `priority`/`label`/`due`/`needs_human`/`assignee` filters +
  `sort`, sharing one filter grammar (structured JSON). `saved_view` table (`board_id`, `name`,
  `query` JSON); `GET/POST/DELETE /api/v1/boards/{id}/views`. MCP + `kan view` verbs. UI: a saved-view
  switcher + a table/list view honoring the active view.
- **Tests:** integration — each filter + combinations; save/list/delete a view; a view's query
  reproduces its result set. e2e — switch views.
- **Acceptance:** save + switch "needs me"; suite green. Additive migration.

## V15 · Full-text search

- **Build:** Postgres FTS — a `tsvector` (generated column or trigger) over `title`+`description`, GIN
  index (migration); `GET /api/v1/cards?q=` ranks by relevance (owner/member-scoped like the rest).
  MCP + `kan list --q`. UI: a search box.
- **Tests:** integration — `q` matches title and description, ranks, respects board access; empty `q`
  is a no-op. e2e — search returns hits.
- **Acceptance:** search demo; suite green. Additive migration.

## V16 · Awareness dashboard (mission control)

- **Build:** a read-first **Dashboard** view (new nav entry): in-flight-by-assignee (join work-links +
  auto-sync PR/CI status), a needs-attention list (from V13), the deepened activity feed (filter by
  actor/action — API gains `actor=`/`action=` on the activity endpoint), and the table + saved-view
  switcher (V14). Poll/refresh only (no websockets). No new write path.
- **Tests:** integration — activity filters; the in-flight query. e2e — dashboard renders in-flight,
  needs-attention, activity; light + dark screenshots (CI-safe via `testInfo.outputPath`).
- **Acceptance:** the mission-control demo; suite green. Frontend + small API extension — deploys.

## V17 · Fleet reporting

- **Build:** `GET /api/v1/boards/{id}/metrics` — throughput (done/period), cycle time
  (created/first-`in_progress`→`done` from the activity feed), aging WIP, per-assignee — all derived,
  no writes. MCP + `kan metrics`. UI: small charts on the Dashboard (follow the dataviz conventions).
- **Tests:** integration — seed activity, assert each metric; empty board → zeroed. Unit — the
  cycle-time/aging computation.
- **Acceptance:** metrics via API + `kan`, charts render; suite green. No migration.

## V18 · Scoped tokens *(Later)*

- **Build:** `personal_access_token.scope` (`read`/`write`, default `write` — existing PATs stay
  writers). Authz denies `Access.WRITE`+ to an agent principal on a `read` PAT (`403`). Tokens UI +
  `kan`/MCP surface the scope at creation.
- **Tests:** integration — a `read` PAT can GET but a write → `403`; a `write`/legacy PAT unaffected.
- **Acceptance:** observer-token demo; suite green. Additive migration.

## V19 · Batch + templates *(Nice-to-have)*

- **Build:** batch create/update endpoints (or extend existing); card/board templates (a `template`
  store + apply). MCP + `kan` verbs.
- **Tests:** integration — batch creates N cards atomically; apply a template yields the expected
  cards.
- **Acceptance:** seed-a-plan-from-template demo; suite green.

---

> **Board mapping.** These slices are tracked on the *Simple Kanban Roadmap* board as M5 epics + cards
> (dogfooding, as always). See the EPIC-`M5:` epics; each V-slice above corresponds to one or more
> cards under the matching epic.
