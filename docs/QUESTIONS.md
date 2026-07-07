# QUESTIONS.md

Scratch file for the grilling process (step A). Status: ⬜ open · ✅ answered · 🚫 out-of-scope.
All A1 questions resolved 2026-07-07. Decisions recorded in CONTEXT.md and docs/adr/.

---

## 1. Domain & vocabulary

- ✅ **Q1.1 Card fields:** `ticket_number, title(req), description(opt, plain text), column,
  position, story_points, assignee, created_at, updated_at`. Priority/labels/due-date cut. (ADR 0006)
- ✅ **Q1.2 Story points:** nullable, Fibonacci enum {1,2,3,5,8,13}, null = unestimated. (ADR 0006)
- ✅ **Q1.3 Assignee:** nullable free-text string, no User entity. (ADR 0006/0007)
- ✅ **Q1.4 Ticket number:** `KAN-<n>` from global Postgres sequence, immutable, never reused. (ADR 0006)
- ✅ **Q1.5 Columns:** fixed enum todo/in_progress/done, no WIP limits, not user-editable. (ADR 0006)
- ✅ **Q1.6 Ordering:** yes — `position` within column; drag-to-reorder supported. (ADR 0006)
- ✅ **Q1.7 Board:** single global implicit board. (ADR 0006)
- ✅ **Q1.8 Lifecycle:** edit + hard-delete; no archive, no history. (ADR 0006)

## 2. API design

- ✅ **Q2.1 Style/surface:** REST+JSON, full CRUD + move + list, OpenAPI at /docs. (ADR 0005)
- ✅ **Q2.2 MCP/CLI readiness:** API-first, UI is just a client; no MCP/CLI code in MVP. (ADR 0005)
- ✅ **Q2.3 Move semantics:** dedicated `POST /api/cards/{id}/move`; PATCH for field edits. (ADR 0006)
- ✅ **Q2.4 Validation:** title required/non-empty, column valid enum, story_points in set|null;
  standard JSON errors. (CONTEXT §4)

## 3. Concurrency & real-time

- ✅ **Q3.1 Multi-user editing:** last-write-wins, no locking. (ADR 0007)
- ✅ **Q3.2 Live updates:** no real-time; refetch on mutate/focus. (ADR 0007)

## 4. Data & persistence

- ✅ **Q4.1 Migrations:** PostgreSQL + Alembic from day one (user decision). (ADR 0002)
- ✅ **Q4.2 Timestamps/soft-delete:** created_at/updated_at yes; no soft-delete. (ADR 0006)
- ✅ **Q4.3 Seed data:** ship a few demo cards. (CONTEXT §7)

## 5. Deployment, hosting & CI/CD

- ✅ **Q5.1 Topology:** FastAPI serves built Svelte bundle — single artifact, no CORS. (ADR 0003)
- ✅ **Q5.2 Repo layout:** monorepo /frontend /backend. (ADR 0001)
- ✅ **Q5.3 Hosting:** Fly.io (app) + Neon (managed Postgres), both free tier. (ADR 0004)
- ✅ **Q5.4 Containerization:** multi-stage Dockerfile → one image. (ADR 0003/0004)
- ✅ **Q5.5 CI/CD:** GH Actions — test+build on PR, deploy to Fly on merge to main, prod only. (ADR 0004)
- ✅ **Q5.6 Config/secrets:** `DATABASE_URL` env; `FLY_API_TOKEN` as GH secret. (ADR 0004)

## 6. Non-functional & scope

- ✅ **Q6.1 Scale:** small (handful of users, few hundred cards); Postgres comfortably sufficient. (CONTEXT §7)
- ✅ **Q6.2 Testing:** backend pytest on API + minimal frontend happy-path smoke. (CONTEXT §7)
- ✅ **Q6.3 Browser/responsive:** desktop-first, usable but not optimized on mobile. (CONTEXT §7)
- ✅ **Q6.4 Non-goals:** auth, billing, multi-board, custom columns, WIP limits, comments, labels,
  attachments, due dates, history, real-time, MCP/CLI/agents. (CONTEXT §8)

---

## A2 — Inconsistency / problem check (added during review)

- ✅ **Q-A2.1 — `position` gaps on delete/move:** hard-delete leaves gaps in `position` values.
  Resolved: treat `position` as a *relative ordering only* (sort key), never assume contiguity;
  reordering rewrites affected rows. No uniqueness constraint across (column, position) required
  for MVP.
- ✅ **Q-A2.2 — Neon scale-to-zero cold starts:** first request after idle may see a short DB
  connection delay. Accepted for MVP demo; note it so it isn't mistaken for a bug.
- ✅ **Q-A2.3 — SPA fallback vs API routes:** FastAPI must serve `index.html` for unknown non-API
  paths (client-side routing) while keeping `/api/*` and `/docs` intact. Flagged for PRD/breadboard
  so routing precedence is explicit.
- ✅ **Q-A2.4 — `story_points` enum vs future flexibility:** stored as nullable int, validated
  against the Fibonacci set at the API layer — future relaxation needs no migration. Confirmed
  consistent between CONTEXT and ADR 0006.

---

## E — Final grill (reconcile shaping/breadboard → CONTEXT/PRD/ADRs)

Reviewed FRAME.md + SHAPING.md + BREADBOARD.md against CONTEXT.md + docs/PRD.md + docs/adr/*.
Findings and resolutions (all applied 2026-07-07):

- ✅ **Q-E1 — Move payload inconsistency:** CONTEXT §4 and PRD said "column *and/or* position" while
  BREADBOARD §6 required both. **Resolved:** `column` required, `position` **optional** — omitted =
  append to end of target column. Updated CONTEXT §4, PRD endpoint table, ADR 0006 (Move bullet),
  BREADBOARD §6 (contract + validation). Agent-friendly and matches drag (which always sends a
  position).
- ✅ **Q-E2 — Column enum storage not captured upstream:** shaping (C7) decided `varchar` + CHECK +
  Pydantic enum (not native PG enum), but CONTEXT/PRD/ADR 0006 only said "enum". **Resolved:**
  clarified in CONTEXT §3, PRD data model, ADR 0006, and recorded the rationale in new **ADR 0008**.
- ✅ **Q-E3 — Implementation stack details undocumented:** sync SQLAlchemy 2.0 + `psycopg` v3, `uv`
  (Python 3.12), `npm` (Node 20+), `svelte-dnd-action` (+ HTML5 fallback), Vite dev-proxy.
  **Resolved:** created **ADR 0008 — Implementation stack details**; summarized in CONTEXT §5.
- ✅ **Q-E4 — Refetch-on-focus over-specified:** CONTEXT §7 implied focus-refetch as if required;
  Shape A only requires refetch-after-mutation. **Resolved:** CONTEXT §7 now marks focus-refetch as
  an optional enhancement.

**No remaining contradictions.** REQS ↔ CONTEXT ↔ PRD ↔ ADRs ↔ FRAME ↔ SHAPING ↔ BREADBOARD are
consistent. Product-planning phase complete.
