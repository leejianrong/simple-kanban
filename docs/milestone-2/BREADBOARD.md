---
shaping: true
---

# Milestone 2 — Shape A Breadboard (Agent-Driven Task Tracking)

Detailing of **Shape A — Standalone MCP adapter (stdio)** from `SHAPING.md` into concrete
affordances + wiring. Notation follows the MVP `../BREADBOARD.md`: **Place**, **UI
affordance** `[button]`/`(field)`, **Non-UI affordance** `/api/...`, **Connection** `A ──▶ B`.

This milestone is backend/agent-centric, so most affordances are **Non-UI**. "Demo-able"
(R8) means observable behaviour — via the board UI, `/docs`, `curl`, or the MCP client.

## Surfaces (Places)

> **Note (ADR 0009):** during V1 the epic became a **first-class entity** (its own `epic` table +
> `EPIC-` ids + `/api/epics`), not a `card` with `kind='epic'`. The affordances below are updated to
> match what shipped; P2–P4 (later slices) are unchanged.

| Place | What it is |
|-------|-----------|
| **S1 · Board View** | Existing SPA. Board shows **stories**, each with its epic-name tag + an epic selector on the story form. A separate **Epics view** (top-bar `Board \| Epics` toggle) creates/reads epics. |
| **S2 · REST API `/api/v1`** | Versioned HTTP surface. The one contract both the SPA and the MCP server call. |
| **S3 · MCP server** | Standalone stdio process wrapping `/api/v1`; the agent's entry point. |
| **S4 · Claude Code** | The MCP client. Connects to S3 via `.mcp.json`. |

## UI affordances (S1 — minimal, for R1.1 demo-ability)

| Affordance | Type | Connection / behaviour |
|-----------|------|------------------------|
| **epic tag** | label on a story card | shows the linked epic's name (title = `EPIC-n · name`); display only |
| **(Epic)** | select in story form | lists existing epics; create + edit ──▶ `POST/PATCH /api/cards {epic_id}` |
| **Board \| Epics** | top-bar toggle | switches the main area between the board and the Epics view (no router) |
| **Epics view** | list + create form | `+ New epic` ──▶ `POST /api/epics {name, description}`; each row rolls up its child stories; Edit/Delete ──▶ `PATCH`/`DELETE /api/epics/{id}` |

## Non-UI affordances

| # | Affordance | Mechanism | Wires to |
|---|-----------|-----------|----------|
| **P1** | `epic` entity + `card.epic_id` | *(ADR 0009)* new `epic` table (own `epic_ticket_seq` → `EPIC-n`; `name` + optional `description`); nullable `card.epic_id` FK → `epic.id` (`ON DELETE SET NULL`); Alembic `0003`. New `/api/epics` CRUD; `epic_id` on `CardCreate`/`CardRead`/`CardUpdate`. | validation P1-v; UI tag/rollup |
| **P1-v** | Epic-link validation | `card.epic_id`, if set, must reference an existing epic → `422` on violation. (Cross-table existence check; a story has zero-or-one epic; epics don't nest → no cycles.) | POST/PATCH cards |
| **P2** | Write-guard token | `Authorization: Bearer <t>`; valid tokens from `API_TOKENS` (comma-sep env). **If `API_TOKENS` is unset → writes stay open** (dev/MVP + existing tests unaffected); if set → mutating routes require a valid token, else `401`. Reads always open. | all POST/PATCH/DELETE/move |
| **P3** | `/api/v1` + `/api` alias | Router re-prefixed to `/cards`; included twice (`/api/v1` canonical, `/api` alias `include_in_schema=False`). `/api/health` unversioned. (See `spike-p3-versioning.md`.) | S2; SPA; MCP |
| **P4** | Filtered/paginated list | `GET /api/v1/cards?column&epic_id&updated_since&limit&cursor`; keyset order `(updated_at, id)`. **Body stays a bare `CardRead[]`** (SPA-compatible); the next cursor rides an **`X-Next-Cursor` response header**. No params → today's full list. *(Built in V3 — the pre-V1 sketch's `kind`/`parent_id` became "no `kind`, use `epic_id`".)* | MCP `list_cards`; SPA |
| **A5** | MCP server (`/mcp`) | Python, official `mcp` SDK, **stdio**. Tools → `/api/v1` via `httpx` with the Bearer token. Own `pyproject.toml`. Tools: `list_cards`, `get_card`, `create_card`, `create_epic`, `update_card`, `move_card`, `delete_card`. | S2 endpoints |
| **A6** | Claude Code wiring | `.mcp.json` launches the stdio server with `KANBAN_API_URL` + `KANBAN_TOKEN`. | S3/S4 |

## Wiring

```
S4 Claude Code ──(stdio)──▶ S3 MCP server ──(httpx + Bearer)──▶ S2 /api/v1/cards ──▶ DB
   tool call                 maps tool→HTTP        P2 guards writes    P1 kind/parent
                                                   P4 filters reads

S1 Board View  ──(fetch /api/v1)──▶ S2  (reads open; writes need token only if API_TOKENS set)
   story epic tag ◀── CardRead {epic_id} + EpicRead {name}
   (Epic) story form ──▶ POST/PATCH /api/v1/cards {epic_id}
   Epics view ──▶ /api/v1/epics  (create/read/edit/delete epics; ADR 0009)

Legacy: any /api/cards  ──(alias, same handlers)──▶ P1–P4 behaviour  (temporary; drop later)
```

## Coverage check (breadboard → requirements)

| Req | Covered by |
|-----|-----------|
| R0 · agent drives app via MCP | A5 + A6 |
| R1.1 · epic/story + parent | P1 + P1-v + UI tag/selector/Epics-view (ADR 0009) |
| R3.1 · agent API-token auth | P2 |
| R4.1 · versioned API | P3 |
| R4.2 · filter + pagination + changed-since | P4 |
| R8 · demo-able slices, MVP-simple | each slice ends in observable behaviour (see `SLICES.md`) |

All in-scope requirements map to an affordance. No open ⚠️ flags. Ready to slice.
