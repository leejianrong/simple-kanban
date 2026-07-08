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

| Place | What it is |
|-------|-----------|
| **S1 · Board View** | Existing SPA. Gains a small epic/story surface (badge + parent ref, kind selector on the form). |
| **S2 · REST API `/api/v1`** | Versioned HTTP surface. The one contract both the SPA and the MCP server call. |
| **S3 · MCP server** | Standalone stdio process wrapping `/api/v1`; the agent's entry point. |
| **S4 · Claude Code** | The MCP client. Connects to S3 via `.mcp.json`. |

## UI affordances (S1 — minimal, for R1.1 demo-ability)

| Affordance | Type | Connection / behaviour |
|-----------|------|------------------------|
| **kind badge** | label on card face | shows `Epic` / `Story`; display only |
| **parent ref** | label on a story card | shows parent epic's ticket (e.g. `↳ KAN-3`) when set |
| **(Kind)** | select in create form | `Epic` / `Story` (default Story) ──▶ `POST /api/v1/cards {kind}` |
| **(Parent epic)** | select in create form | shown when Kind=Story; lists existing epics ──▶ `{parent_id}` |

## Non-UI affordances

| # | Affordance | Mechanism | Wires to |
|---|-----------|-----------|----------|
| **P1** | `card.kind` + `card.parent_id` | `kind` varchar+CHECK (`epic`\|`story`, default `story`); `parent_id` nullable self-FK; Alembic `0003`. Added to `CardRead`/`CardCreate`; `parent_id` editable via `CardUpdate`. | validation P1-v; UI badges |
| **P1-v** | Parent validation | A `story` may reference an `epic` parent; an `epic` has no parent; `parent_id` must exist and be `kind=epic`; no self-parent. (Epics can't nest → no cycles.) → `422` on violation | POST/PATCH |
| **P2** | Write-guard token | `Authorization: Bearer <t>`; valid tokens from `API_TOKENS` (comma-sep env). **If `API_TOKENS` is unset → writes stay open** (dev/MVP + existing tests unaffected); if set → mutating routes require a valid token, else `401`. Reads always open. | all POST/PATCH/DELETE/move |
| **P3** | `/api/v1` + `/api` alias | Router re-prefixed to `/cards`; included twice (`/api/v1` canonical, `/api` alias `include_in_schema=False`). `/api/health` unversioned. (See `spike-p3-versioning.md`.) | S2; SPA; MCP |
| **P4** | Filtered/paginated list | `GET /api/v1/cards?kind&column&parent_id&updated_since&limit&cursor`; keyset order `(updated_at, id)`. **Body stays a bare `CardRead[]`** (SPA-compatible); the next cursor rides an **`X-Next-Cursor` response header**. No params → today's full list. | MCP `list_cards`; SPA |
| **A5** | MCP server (`/mcp`) | Python, official `mcp` SDK, **stdio**. Tools → `/api/v1` via `httpx` with the Bearer token. Own `pyproject.toml`. Tools: `list_cards`, `get_card`, `create_card`, `create_epic`, `update_card`, `move_card`, `delete_card`. | S2 endpoints |
| **A6** | Claude Code wiring | `.mcp.json` launches the stdio server with `KANBAN_API_URL` + `KANBAN_TOKEN`. | S3/S4 |

## Wiring

```
S4 Claude Code ──(stdio)──▶ S3 MCP server ──(httpx + Bearer)──▶ S2 /api/v1/cards ──▶ DB
   tool call                 maps tool→HTTP        P2 guards writes    P1 kind/parent
                                                   P4 filters reads

S1 Board View  ──(fetch /api/v1)──▶ S2  (reads open; writes need token only if API_TOKENS set)
   kind badge / parent ref ◀── CardRead {kind, parent_id}
   (Kind)/(Parent) form ──▶ POST /api/v1/cards {kind, parent_id}

Legacy: any /api/cards  ──(alias, same handlers)──▶ P1–P4 behaviour  (temporary; drop later)
```

## Coverage check (breadboard → requirements)

| Req | Covered by |
|-----|-----------|
| R0 · agent drives app via MCP | A5 + A6 |
| R1.1 · epic/story + parent | P1 + P1-v + UI badges/selectors |
| R3.1 · agent API-token auth | P2 |
| R4.1 · versioned API | P3 |
| R4.2 · filter + pagination + changed-since | P4 |
| R8 · demo-able slices, MVP-simple | each slice ends in observable behaviour (see `SLICES.md`) |

All in-scope requirements map to an affordance. No open ⚠️ flags. Ready to slice.
