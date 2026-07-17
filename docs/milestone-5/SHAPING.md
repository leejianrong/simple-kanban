---
shaping: true
---

# Milestone 5 — Shaping (Human↔agent coordination surface)

The architecture direction was settled collaboratively (see [FRAME](FRAME.md) and the M5 planning
discussion), so this records a **single shape-of-record** — Shape A, the two-surface board — with one
confirming fit check, rather than a multi-shape bake-off. Component-level alternatives are called out
inline where a genuine choice existed (e.g. the `needs_human` mechanism).

## Competitive delta (why these requirements)

What the incumbents lean on, whether we have it, and whether it fits the "simple, API-first,
no-real-time, agent-native" ethos. This is the source of the requirements below.

| Capability | Who leans on it | Have it? | In M5? |
|---|---|---|---|
| Labels/tags, **priority**, due dates | Trello, Linear, Jira | ❌ | ✅ (R4) |
| Deterministic **dispatch** + fleet-safe claim | *(none — agent-native, our moat)* | partial (`claim_card`) | ✅ (R1) |
| Table/list view, **saved views**, search | Jira (JQL), Linear, GH Projects | ❌ (query API, not persisted) | ✅ (R2) |
| Reports/insights (cycle time, throughput) | Jira, Linear | ❌ | ✅ (R2) |
| Scoped agent tokens (read-only vs write) | *(agent-native)* | ❌ (PATs are un-scoped) | ✅ Later (R1.4) |
| Card dependencies, comments, work-links, PR auto-sync, activity feed, membership | Jira/Linear | ✅ (M4) | reused, not rebuilt |
| Configurable columns / workflow engine, sub-tasks | Jira, Trello | ❌ | ❌ (a `needs_human` flag, not a column; deferred otherwise) |
| Attachments/file upload, custom-field explosion, time tracking, transition rules | Jira | ❌ | ❌ (off-ethos — the "stay simple" line) |
| Real-time collaboration / websockets | all | ❌ by design | ❌ (ADR 0007 reaffirmed) |

**Best ideas adopted:** Trello → labels, due dates (radical simplicity). Linear → priority, clean
saved views, PR-auto-status (we already match via M4 auto-sync). Jira → a query language + reports
(not its workflow engine). GitHub Projects → multiple views over one dataset. **Deliberately not
adopted:** Jira's workflow/permission engine, time tracking, attachments (needs storage infra).

---

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| **R0** | **A human directs a fleet of bring-your-own LLM agents through the board: agents operate it end-to-end via a frictionless, fleet-safe API/MCP/CLI; the human observes and steers via a glanceable UI + the CLI — with no real-time infra** | Core goal |
| **R1** | **Agent operating ergonomics (write side)** | |
| R1.1 | An agent can request the **next actionable card** — in `todo`, not blocked by an open dependency, highest **priority** first — for a board (optionally filtered) | Must-have |
| R1.2 | Dispatch is **fleet-safe**: N agents asking concurrently each get a *different* card and never double-work one (atomic select-and-claim; sets assignee + moves to `in_progress`) | Must-have |
| R1.3 | Every new capability has **full API / MCP / CLI parity** in the same slice — thin adapters over `/api/v1` (ADR 0005) | Must-have |
| R1.4 | **Scoped tokens** — an *observer* (read-only) vs *operator* (write) PAT, so an agent gets least-privilege access | Later |
| R1.5 | **Batch + templates** — create/act on many cards at once; card/board templates for recurring work | Nice-to-have |
| **R2** | **Human awareness UI (read side)** | |
| R2.1 | A glanceable **fleet-status** view: what's in flight, **by which agent**, with linked PR / CI status (from M4 work-links + auto-sync) | Must-have |
| R2.2 | A **"needs your attention"** surface listing cards an agent has flagged for a human decision (driven by R3.1) | Must-have |
| R2.3 | **Activity / history** is a first-class read experience ("what did my agents do") — deepen the M4 (KAN-18) feed | Must-have |
| R2.4 | Alternate views over one dataset: a **table/list view**, and **saved views** (named, persisted queries) | Must-have |
| R2.5 | **Full-text search** across cards (title + description) | Must-have |
| R2.6 | The UI is **read/awareness-first** — a human never has to do CRUD to run the board (they still can, but it isn't the primary path) | Must-have |
| **R3** | **Human↔agent handoff** | |
| R3.1 | A lightweight **`needs_human` flag** on a card (with an optional note) that an agent sets when it needs a decision — queryable; does **not** alter the column model | Must-have |
| R3.2 | The human resolves the flag by **instructing via the CLI / a card comment**; the agent can **discover the resolution** (flag cleared + comment/activity) and resume | Must-have |
| R3.3 | Optional per-board **"require approval to reach `done`"** gate | Later |
| **R4** | **Card fields (serve both audiences)** | |
| R4.1 | **`priority`** — an enum (`none`/`low`/`medium`/`high`/`urgent`), settable by agents + humans; dispatch (R1.1) respects it | Must-have |
| R4.2 | **Labels** — board-scoped, colored, filterable tags on cards (routing + categorization) | Must-have |
| R4.3 | **`due_date`** — optional; surfaces an *overdue* signal | Must-have |
| **R5** | **Constraints (non-functional)** | |
| R5.1 | Preserve **no-real-time / LWW** (ADR 0007) — awareness via poll/refresh; fleet-safety via a DB primitive (`FOR UPDATE SKIP LOCKED`), not app locking | Must-have |
| R5.2 | **Single-origin** serving preserved; no new cross-origin/CORS surface | Must-have |
| R5.3 | **Additive & back-compat** — existing boards/cards/tokens keep working; migrations add nullable columns / new tables only | Must-have |
| R5.4 | **Bring-your-own-agent** — build the substrate, not the agent/orchestrator; no chat integration in M5 (Telegram/Slack is M6+) | Must-have |
| R5.5 | Hold the **"stay simple"** line — no workflow engine, custom-field explosion, time tracking, or attachments | Must-have |
| **R6** | Ships as **demo-able vertical slices behind CI**, matching the established cadence (carried from M2–M4) | Must-have |

---

## Decisions log

- **Two surfaces, one board.** Agents own the *write* path (API/MCP/CLI); the UI is the human's
  *read/awareness* path. UI editing ergonomics (drag-drop, forms) are explicitly **not** an M5 focus.
- **Interaction model = autonomous dispatch + review, with a comment-thread handoff** (Model 1 + the
  needs-human flag). Agents pull ready cards and run them; when stuck, they raise `needs_human`; the
  human answers via CLI/comment. Approval-everywhere (Model 3) is a deferred opt-in (R3.3).
- **`needs_human` is a flag, not a column** (maintainer decision). Keeps the `todo/in_progress/done`
  model intact and stays independently queryable/filterable. (Alternative — a real `review` column —
  rejected: it would fork the column model and the per-(board,column) position logic.)
- **Fleet-safety via `SELECT … FOR UPDATE SKIP LOCKED`**, not application locks or leases — a
  transaction-scoped DB primitive, consistent with ADR 0007's "no locking" (LWW still governs plain
  edits). A crashed agent simply leaves a card `in_progress`; the human sees it stalled in the
  awareness UI (no lease/TTL machinery in M5).
- **Priority as `varchar` + CHECK**, mirroring the `column` convention (ADR 0008) — a new value needs
  no `ALTER TYPE`.
- **Reports are derived, not stored** — computed from the M4 activity feed + card timestamps, so the
  metrics API adds no write path.

## Open questions (resolve during slicing)

- Labels: a `label` table + `card_label` join (board-scoped, colored — chosen) vs a plain `text[]`
  (simpler but not first-class/colored). Leaning join table.
- Saved views: store the query as structured JSON vs an opaque query string. Leaning structured JSON
  so the CLI/MCP and UI share one filter grammar.
- Metrics surface: one `GET /boards/{id}/metrics` bundle vs per-metric endpoints. Leaning one bundle.

---

## Shape A — Two-surface board: agents operate, humans observe

Parts are vertical slices (mechanism + its data), traced to the R's they satisfy.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | **Card fields.** Migrations (additive, nullable): `card.priority` (`varchar` + CHECK `none/low/medium/high/urgent`, default `none`), `card.due_date` (`timestamptz` null). Labels: `label` table (`board_id`, `name`, `color`) + `card_label` M:N join. Schemas + query filters (`priority`, `label`, `due_before`, overdue) + label chips / priority + due on the card UI. **API+MCP+CLI parity.** (R4.1–R4.3, R1.3) | |
| **A2** | **Dispatch + fleet-safe claim.** `POST /api/v1/boards/{id}/dispatch` (optional `assignee`, label/priority filters): one transaction — `SELECT` the next `todo`, un-blocked card ordered by `priority DESC, position` `FOR UPDATE SKIP LOCKED`, set `assignee`, move to `in_progress`, record activity, return it (or `204` if none ready). Also `GET …/next` (peek, no claim). (R1.1, R1.2, R5.1) | |
| **A3** | **`needs_human` handoff.** Additive `card.needs_human` (bool, default false) + `card.attention_note` (text null). Endpoints to raise/clear (`POST /cards/{id}/needs-human`, `…/resolve`); records `attention`/`resolved` activity actions (CHECK-vocabulary migration, mirroring EPIC-4's `restored`). Query filter `needs_human=true`. Resolution channel = existing comments. **API+MCP+CLI parity.** (R3.1, R3.2) | |
| **A4** | **Scoped tokens.** Add `personal_access_token.scope` (`read`/`write`, default `write` for back-compat). Authz: an agent principal on a `read` PAT is denied `Access.WRITE`+ (`403`). Tokens UI + `kan`/MCP surface the scope at creation. (R1.4 — Later) | |
| **A5** | **Query depth + saved views.** Extend the V3 query API with `priority`/`label`/`due`/`needs_human`/`assignee` filters + sort (a small "JQL-lite" grammar). `saved_view` table (`board_id`, `name`, `query` JSON); CRUD API + a view switcher. **API+MCP+CLI parity.** (R2.4) | |
| **A6** | **Full-text search.** Postgres FTS: a `tsvector` (generated column or trigger) over `title`+`description`, GIN index; `GET /api/v1/cards?q=` ranks matches. **API+MCP+CLI parity.** (R2.5) | |
| **A7** | **Awareness UI (mission control).** A read-first Dashboard view: *in-flight by assignee* (with PR/CI status from work-links + auto-sync), a *needs-attention* list (A3), and the activity feed deepened (filter by actor/agent, entity, action) front-and-centre; plus a **table view** + the saved-view switcher (A5). Poll/refresh (R5.1). (R2.1, R2.2, R2.3, R2.4, R2.6) | |
| **A8** | **Fleet reporting.** `GET /api/v1/boards/{id}/metrics`: throughput (done/period), cycle time (created/first-`in_progress`→`done` from the activity feed), aging WIP, per-assignee breakdown — all derived, no new writes. Small UI charts. **API+MCP+CLI parity.** (R2.3) | |
| **A9** | **Batch + templates.** Batch create/update; card/board templates for recurring work. (R1.5 — Nice-to-have, late slice) | |

## Fit Check — R × A

| Req | Requirement | Status | A |
|-----|-------------|--------|---|
| R0 | Human directs a BYO agent fleet; agents operate, human observes; no real-time | Core goal | ✅ |
| R1.1 | Next actionable card (todo, unblocked, priority-ordered) | Must-have | ✅ (A2) |
| R1.2 | Fleet-safe dispatch (atomic select-and-claim, no double-work) | Must-have | ✅ (A2) |
| R1.3 | Full API/MCP/CLI parity per slice | Must-have | ✅ (A1,A3,A5,A6,A8) |
| R1.4 | Scoped observer/operator tokens | Later | ✅ (A4) |
| R1.5 | Batch + templates | Nice-to-have | ✅ (A9) |
| R2.1 | Fleet-status view (in flight by agent + PR/CI) | Must-have | ✅ (A7) |
| R2.2 | "Needs your attention" surface | Must-have | ✅ (A7←A3) |
| R2.3 | Activity/history read experience + reporting | Must-have | ✅ (A7,A8) |
| R2.4 | Table view + saved views | Must-have | ✅ (A5,A7) |
| R2.5 | Full-text search | Must-have | ✅ (A6) |
| R2.6 | Read/awareness-first UI (no CRUD required to operate) | Must-have | ✅ (A7) |
| R3.1 | `needs_human` flag (queryable, not a column) | Must-have | ✅ (A3) |
| R3.2 | Resolve via CLI/comment; agent discovers resolution | Must-have | ✅ (A3) |
| R3.3 | Optional per-board approval gate | Later | ✅ (A3 extends; late) |
| R4.1 | `priority` enum, dispatch respects it | Must-have | ✅ (A1,A2) |
| R4.2 | Board-scoped colored labels | Must-have | ✅ (A1) |
| R4.3 | `due_date` + overdue signal | Must-have | ✅ (A1) |
| R5.1 | Preserve no-real-time/LWW; DB-primitive fleet-safety | Must-have | ✅ (A2,A7) |
| R5.2 | Single-origin preserved | Must-have | ✅ |
| R5.3 | Additive & back-compat migrations | Must-have | ✅ (A1,A3,A4) |
| R5.4 | BYO agent; no chat integration in M5 | Must-have | ✅ |
| R5.5 | Stay-simple line held | Must-have | ✅ |
| R6 | Demo-able vertical slices behind CI | Must-have | ✅ |

**Notes:** No ❌ — Shape A is the confirmed shape-of-record. R1.4 (scoped tokens), R1.5 (batch/templates)
and R3.3 (approval gate) are real but marked *Later/Nice-to-have* and land in the tail slices; the
milestone is demo-complete without them.

---

## Detail A — Affordances (breadboard)

### UI affordances (human read/awareness surface)

| Affordance | Place | Wires out |
|---|---|---|
| **Dashboard** nav entry | top bar (beside Board/Epics/Activity) | → Dashboard view |
| In-flight-by-assignee panel | Dashboard | → `GET /cards?column=in_progress` (+ work-links/PR status) |
| Needs-attention list | Dashboard | → `GET /cards?needs_human=true`; row → card detail |
| Deepened activity feed (actor/action filters) | Dashboard / Activity | → `GET /boards/{id}/activity?actor=&action=` |
| Metrics cards + charts | Dashboard | → `GET /boards/{id}/metrics` |
| Table view (sortable columns) | Board area (view toggle) | → query API |
| Saved-view switcher | top bar / view area | → `GET/POST /boards/{id}/views` |
| Search box | top bar | → `GET /cards?q=` |
| Priority badge · label chips · due/overdue pill | Card | (display; edits via API/CLI) |
| Needs-human badge | Card / Column | → `needs_human` |

### Non-UI affordances (agent operate surface + data)

| Affordance | Kind | Wires out |
|---|---|---|
| `card.priority`, `card.due_date` | column (migration) | — |
| `label` / `card_label` | tables (migration) | — |
| `card.needs_human`, `card.attention_note` | column (migration) | — |
| `personal_access_token.scope` | column (migration) | authz |
| `saved_view` | table (migration) | — |
| `card` FTS `tsvector` + GIN index | migration | search |
| `POST /boards/{id}/dispatch`, `GET /boards/{id}/next` | endpoints | ordering + `FOR UPDATE SKIP LOCKED` |
| `POST /cards/{id}/needs-human`, `/resolve` | endpoints | activity |
| `GET/POST/DELETE /boards/{id}/views` | endpoints | `saved_view` |
| `GET /boards/{id}/metrics` | endpoint | activity feed + timestamps |
| query API filters (`priority`,`label`,`due`,`needs_human`,`assignee`,`q`) + sort | handler | — |
| MCP tools + `kan` verbs for all of the above | adapters | `/api/v1` |

Slicing follows in [SLICES.md](SLICES.md).
