---
shaping: true
---

# Milestone 2 — Agent-Driven Task Tracking (Shaping)

Working document. Frame in `FRAME.md`. MVP baseline in `../` + `../adr/`.
Phase: **Shaping** — scope selected (**Lean agent-loop first**); shapes sketched.

Status legend: **Core goal** · **Must** (must ship for the milestone) · **Leaning yes**
· **Nice-to-have** · **Undecided** · **Later** (real, but a future milestone) · **Out**.

**Scope decision (negotiated):** *Lean agent-loop first* — prove Claude Code driving the
board end-to-end with the fewest ADR reversals. Multi-board (R2), human OAuth + authz
(R3.2/3.3), audit/soft-delete (R5), GitHub linkage (R6), and real-time (R7) are **Later**.

---

## Requirements (R)

Statuses reflect the **Lean** cut. 🟡 = changed from the initial proposal.

| ID | Requirement | Status |
|----|-------------|--------|
| **R0** | An agent (e.g. Claude Code) can perform the app's actions programmatically through an MCP server | **Core goal** |
| **R1** | The board can represent this project's real work: epics, stories, and useful metadata | **Must** |
| R1.1 | A card can be an epic or a story, and a story can belong to a parent epic | Must |
| R1.2 | Cards carry labels and a priority | 🟡 Later |
| R1.3 | Card descriptions support Markdown | 🟡 Later |
| **R2** | Work can be organized into more than one board | 🟡 **Later** |
| R2.1 | Multiple named boards can exist | 🟡 Later |
| R2.2 | Every card belongs to exactly one board | 🟡 Later |
| R2.3 | Ticket numbers stay unique and meaningful across boards (per-board prefix?) | 🟡 Later |
| **R3** | The publicly-deployed app is safe to expose to writers | **Must** |
| R3.1 | Agents authenticate non-interactively (API token) | Must |
| R3.2 | Humans authenticate (GitHub OAuth) for the UI | Later |
| R3.3 | Authorization: a writer can only affect boards they're permitted to | 🟡 Later |
| R3.4 | Agent tokens are scoped (read vs write) and revocable | 🟡 Later |
| **R4** | The API is ergonomic for programmatic clients | **Must** |
| R4.1 | The API is versioned so clients don't break when it evolves | Must |
| R4.2 | Cards can be queried by filter, with pagination and a "changed since" cursor | Must |
| R4.3 | Writes are idempotent (safe retries) and support batching (bulk create) | 🟡 Later |
| **R5** | Changes are trustworthy and reversible | 🟡 **Later** |
| R5.1 | An audit trail records who changed what and when (human vs which agent) | 🟡 Later |
| R5.2 | Deletes are recoverable (soft delete / undo) | 🟡 Later |
| R5.3 | Failures during autonomous operation are observable (logging / error tracking) | Nice-to-have |
| **R6** | The board is wired into the project's real GitHub workflow | **Later** |
| R6.1 | Cards link to commits / PRs and reflect their status | Later |
| R6.2 | A board can be populated from an existing plan (docs → cards) in bulk | 🟡 Later |
| **R7** | The UI reflects changes made by other writers without a manual reload (real-time) | 🟡 **Later** |
| **R8** | Each capability ships as a demo-able vertical slice behind CI/PR, staying MVP-simple | **Must** |

**In scope for v0.2:** R0, R1.1, R3.1, R4.1, R4.2, R8. Everything else → Later.

> Note on R1.1 demo-ability (R8): the UI currently has no epic/story concept. Minimum
> visible surface = show a card's `kind` (epic/story badge) and, for a story, its parent
> epic's ticket. Full epic-rollup UI is not required this milestone.

---

## Shapes

All in-scope shapes share the same **app-side changes** (P1–P4) — the fork is only *how
the MCP interface is delivered* (P5/P6). Shared parts extracted per shaping guidance.

### Shared parts (P) — needed by every shape

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **P1** | **Epic/story model.** Card gains `kind` varchar+CHECK (`epic`\|`story`, default `story`) and nullable `parent_id` self-FK; Alembic migration; validation: a `story` may reference an `epic` parent, an `epic` has no parent. Mirrors the `column` enum pattern (ADR 0008). | |
| **P2** | **API token auth.** `Authorization: Bearer <token>`; valid tokens from env (`API_TOKENS`, comma-sep). A FastAPI dependency guards all **mutating** routes (POST/PATCH/DELETE/move); reads stay open for the SPA. 401 on missing/bad token. | |
| **P3** | 🟡 **API versioning (spike-resolved).** Re-prefix the cards router to `/cards`; include it twice in `main.py` — `/api/v1` (canonical) + `/api` (compat alias, `include_in_schema=False`). SPA (5 refs) + e2e (3 refs) move to `/api/v1`; backend tests stay on the alias for now + one new versioning test. `/api/health` stays unversioned. See `spike-p3-versioning.md`. | |
| **P4** | **Query API.** `GET /api/v1/cards` gains `kind`, `column`, `parent_id`, `updated_since`, `limit`, `cursor`; keyset pagination ordered by `(updated_at, id)`; response carries a next-cursor. Back-compat: no params = today's behaviour. | |

### A: Standalone MCP adapter (stdio)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| A1–A4 | = P1–P4 | |
| **A5** | **Standalone MCP server** in `/mcp` (Python, official `mcp` SDK, **stdio** transport). Tools: `list_cards`, `get_card`, `create_card`, `create_epic`, `update_card`, `move_card`, `delete_card`. Thin wrapper calling `/api/v1` over httpx with the Bearer token. Own `pyproject.toml`. | ⚠️ |
| **A6** | **Claude Code wiring**: an `.mcp.json` snippet launching the stdio server with `KANBAN_API_URL` + `KANBAN_TOKEN` env. Points at local backend (dev) or prod. | |

### B: Embedded MCP endpoint (HTTP/SSE)

| Part | Mechanism | Flag |
|------|-----------|:----:|
| B1–B4 | = P1–P4 | |
| **B5** | **MCP mounted inside FastAPI** (HTTP/SSE transport, e.g. an MCP ASGI sub-app at `/mcp`). Tools call the service functions **in-process** (no HTTP hop). Deployed as part of the single artifact. | ⚠️⚠️ |
| **B6** | **Claude Code wiring**: remote MCP URL + token header; MCP auth over HTTP/SSE. | ⚠️ |

### Fit Check

| Req | Requirement | Status | A | B |
|-----|-------------|--------|---|---|
| R0 | An agent can perform the app's actions programmatically through an MCP server | Core goal | ✅ | ❌ |
| R1.1 | A card can be an epic or a story, and a story can belong to a parent epic | Must | ✅ | ✅ |
| R3.1 | Agents authenticate non-interactively (API token) | Must | ✅ | ✅ |
| R4.1 | The API is versioned so clients don't break when it evolves | Must | ✅ | ✅ |
| R4.2 | Cards can be queried by filter, with pagination and a "changed since" cursor | Must | ✅ | ✅ |
| R8 | Each capability ships as a demo-able vertical slice behind CI/PR, staying MVP-simple | Must | ✅ | ❌ |

**Notes:**
- B fails R0 and R8: B5/B6 are flagged unknowns (in-process MCP-over-HTTP/SSE library
  maturity, MCP-over-HTTP auth, interaction with the SPA catch-all route). Per shaping
  rules a flagged mechanism can't claim ✅. A uses the mature stdio path — the standard
  local Claude Code integration — so it is understood end-to-end.
- P3 was flagged; **resolved by `spike-p3-versioning.md`** (dual-mount `/api/v1` + `/api`
  alias, migrate SPA/e2e, keep tests on the alias). No open flags remain in Shape A.

### Selected shape: **A — Standalone MCP adapter (stdio)**

Rationale: passes the full fit check; stdio is the simplest, most mature Claude Code
integration; keeps the MCP server decoupled from the web app's deploy; matches the
"lean, MVP-simple" appetite (R8). B (embedded HTTP MCP) is a sound *later* evolution once
remote/multi-client access matters — logged, not built.

---

## Next actions

- [x] Spike P3 — `/api` → `/api/v1` move (see `spike-p3-versioning.md`; flag resolved)
- [x] Breadboard Shape A → `BREADBOARD.md` (affordances + wiring + coverage, no open flags)
- [x] Slice into demo-able increments → `SLICES.md` (V1–V5, each a PR behind CI)
- [ ] Build V1 (epic/story model + badges), then V2–V5 in order
