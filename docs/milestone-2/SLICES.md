---
shaping: true
---

# Milestone 2 — Slices (Shape A)

Vertical increments of the breadboard (`BREADBOARD.md`). Each ends in **observable
behaviour** and ships as its own PR behind CI (R8), matching the MVP cadence. Order
respects dependencies: V5 (MCP) needs the versioned path (V2), token (V4), and query (V3);
V1 is foundational + immediately visible.

| Slice | Parts | Ends in (demo) |
|-------|-------|----------------|
| **V1 · Epic/story model + badges** | P1, P1-v, UI | Create an epic and a story under it in the UI; Epic/Story badges + the story's `↳ KAN-n` parent ref render and survive reload |
| **V2 · API versioning** | P3 | `/docs` shows `/api/v1/*`; SPA still works; `curl` both `/api/v1/cards` and the `/api/cards` alias |
| **V3 · Query API** | P4 | `curl "/api/v1/cards?kind=epic"`, `?updated_since=…`, `?limit=2` (+ `X-Next-Cursor` header) return the right filtered/paged results |
| **V4 · Agent token auth** | P2 | With `API_TOKENS` set: write without token → `401`, with token → `201`; reads open. Unset → open (unchanged) |
| **V5 · MCP server + Claude Code** | A5, A6 | Claude Code, via MCP, creates an epic + stories and moves one — the cards appear on the board. **The milestone demo.** |

---

## V1 · Epic/story model + card-face badges

- **Build:** `kind` (varchar+CHECK, default `story`) + `parent_id` (nullable self-FK) on
  `card`; Alembic `0003`; add to `CardRead`/`CardCreate`, `parent_id` to `CardUpdate`.
  Validation P1-v (story→epic parent; epic has no parent; parent must be an existing epic).
  UI: kind badge + parent ref on the card face; Kind select + (for stories) parent-epic
  select in `CardForm`.
- **Tests:** integration — default `kind=story`; create epic; story with valid epic parent;
  reject epic-with-parent; reject non-epic / missing parent; PATCH re-parent. e2e — create
  epic then story-under-epic, assert badges + parent ref visible.
- **Acceptance:** the demo above works; full suite green.

## V2 · API versioning (`/api/v1` + alias)

- **Build:** re-prefix router to `/cards`; include twice (`/api/v1`, `/api` alias hidden
  from schema); migrate `api.ts` (5 refs) + e2e (3 refs) to `/api/v1`. `/api/health`
  unchanged. (Per `spike-p3-versioning.md`.)
- **Tests:** new `test_versioning.py` — `/api/v1/cards` works **and** `/api/cards` alias
  works; existing suites stay green (they ride the alias).
- **Acceptance:** `/docs` lists only `/api/v1/*` (+ health); SPA + e2e green on `/api/v1`.

## V3 · Query API (filter / pagination / changed-since)

- **Build:** `kind`, `column`, `parent_id`, `updated_since`, `limit`, `cursor` on
  `GET /api/v1/cards`; keyset pagination `(updated_at, id)`; next cursor via `X-Next-Cursor`
  header; **body stays a bare `CardRead[]`** (SPA unaffected); no params → full list.
- **Tests:** integration — each filter; `updated_since` boundary; `limit` + cursor paging
  returns disjoint pages; empty result; back-compat (no params = all).
- **Acceptance:** the `curl` demos above return correct results.

## V4 · Agent token auth (writes)

- **Build:** `require_token` dependency on POST/PATCH/DELETE/move (both mounts). Tokens from
  `API_TOKENS` env. **Unset → writes open** (existing tests + local dev unaffected); set →
  enforced, `401` on missing/bad. Reads always open.
- **Tests:** a suite that sets `API_TOKENS` — write without/with-bad token → `401`, with
  token → `201`, GET open. Existing write tests run with `API_TOKENS` unset (unchanged).
- **Acceptance:** the 401/201 demo works; prod sets `API_TOKENS` (Fly secret).

## V5 · MCP server + Claude Code wiring

- **Build:** `/mcp` package (own `pyproject.toml`) — official `mcp` SDK, stdio; tools
  `list_cards` / `get_card` / `create_card` / `create_epic` / `update_card` / `move_card` /
  `delete_card`, each mapping to `/api/v1` via `httpx` with `KANBAN_TOKEN`. `.mcp.json`
  snippet + README for Claude Code (`KANBAN_API_URL`, `KANBAN_TOKEN`).
- **Tests:** unit — each tool issues the expected request (mocked httpx) and maps errors;
  a smoke that the server advertises the tool list. (Optional: end-to-end against a live
  test API.)
- **Acceptance:** connect Claude Code; it lists/creates/moves cards via MCP; changes show
  on the board. Then dogfood: seed this repo's own epics/stories via the agent.

---

## Notes / decisions folded in

- **Pagination via header, not envelope** (P4): keeps `GET /cards` returning a bare array so
  the SPA `listCards(): Card[]` is untouched — back-compat over a cleaner envelope.
- **Auth off when `API_TOKENS` unset** (P2): preserves MVP/dev behaviour and avoids churning
  ~40 existing write tests; prod opts in via a Fly secret.
- **`/api` alias kept temporarily** (P3): SPA + e2e move to `/api/v1`; the ~61 backend-test
  literals stay on the alias for now; sweep + drop alias is a later chore.
- **CI:** V5 adds an `/mcp` package — extend CI with an mcp unit-test job (mirrors the
  backend jobs); e2e/backend jobs unchanged.
