# V3 session prompt — Query API (filter / pagination / changed-since)

Copy the block below into a **new** chat session to build Milestone 2 slice **V3
(query API on `GET /api/v1/cards`)**.

**Before running it:** merge PR #13 (drop the `/api` alias; sweep tests to `/api/v1`) so V3
branches off a `main` where `/api/v1` is the sole prefix and the backend tests already ride it.

> ⚠️ **The shaped V3 spec is stale — it predates V1's reshape (ADR 0009).** `SHAPING.md` /
> `BREADBOARD.md` / `SLICES.md` describe the params as `kind`, `column`, `parent_id`,
> `updated_since`, `limit`, `cursor`. Two of those no longer exist in the schema:
> - **`kind`** — there is no `kind` column. Cards *are* stories; epics are a separate table
>   queried at `/api/v1/epics`. Drop the `kind` filter entirely.
> - **`parent_id`** → **`epic_id`** (the nullable FK `card.epic_id`).
>
> The block below already reflects the real schema. Verify against the code anyway.

---

```
You're picking up an in-progress project on disk: `simple-kanban`, a deployed MVP kanban app
(FastAPI + sync SQLAlchemy/psycopg on Postgres, Svelte 5 + Vite SPA, single artifact). The MVP
is feature-complete and deployed. Milestone 2 "Agent-Driven Task Tracking" is underway: V1 (epic
as a first-class entity + Epics view) and V2 (API versioning — everything under `/api/v1`, the
temporary `/api` alias since dropped) are merged. Build its NEXT slice, V3, following the same
slice-behind-a-PR cadence.

READ THESE FIRST — they are authoritative:
- CLAUDE.md — repo conventions (branch/PR workflow, commands, architecture). Follow it exactly.
- docs/milestone-2/SLICES.md (§ V3), BREADBOARD.md (P4), SHAPING.md (P4).
- docs/adr/0006 (data model), 0008 (sync SQLAlchemy + psycopg v3), 0009 (epic entity).
- The current backend/app/ (routers/cards.py, ordering.py, models.py, schemas.py) and
  frontend/src/lib/api.ts + frontend/src/lib/board.svelte.ts.

IMPORTANT — the shaped V3 plan predates V1's reshape (ADR 0009), so DO NOT trust its param
list; verify against the code. SHAPING/BREADBOARD/SLICES say the query params are
`kind`, `column`, `parent_id`, `updated_since`, `limit`, `cursor`. In the CURRENT schema:
- There is NO `kind` column — a card is always a story; epics are a separate table
  (`/api/v1/epics`). DROP the `kind` filter; it is meaningless now.
- `parent_id` is now the nullable FK `card.epic_id`. Use `epic_id`, not `parent_id`.
Re-read models.py / schemas.py before writing any filter.

SCOPE — build V3 ONLY: the query API on `GET /api/v1/cards`. Do NOT build V4 (token auth) or
V5 (MCP server) — separate later slices. Keep V3 to the CARDS list; leave `/api/v1/epics` as a
plain full list (epics are few; the SPA's listEpics stays untouched).

WHAT V3 IS:
- `GET /api/v1/cards` gains optional query params, all combinable (AND-ed):
  - `column` — one of todo | in_progress | done (reuse ColumnEnum; 422 on bad value).
  - `epic_id` — stories linked to that epic. (Decide + document how to request "unassigned",
    i.e. epic_id IS NULL — e.g. a sentinel like `epic_id=none`, or leave out of V3 and note it.)
  - `updated_since` — ISO-8601 timestamp; return cards changed after it (the "changed since"
    cursor for polling agents). DEFINE and test the boundary (recommend strictly-greater `>`;
    document it either way).
  - `limit` — max rows this page (validate a sane range, e.g. 1..200; reject/clamp out-of-range
    — pick one and document).
  - `cursor` — opaque keyset cursor from a previous page's `X-Next-Cursor` header.
- Keyset (seek) pagination, NOT offset: order by `(updated_at, id)` and page with a
  `(updated_at, id) > (cursor_updated_at, cursor_id)` predicate. Encode the cursor opaquely
  (e.g. base64 of `updated_at|id`); decode-failure → 422. Return the next cursor ONLY when a
  full page was returned, via an **`X-Next-Cursor` response header** (absent on the last page).
- The response BODY stays a bare `CardRead[]` (NOT an envelope), so the SPA is unaffected.
  With no query params, behaviour is unchanged: the full list.
- Ordering note: the SPA re-sorts client-side by `position` within each column
  (board.svelte.ts `cardsFor`), so switching the list's default DB order to `(updated_at, id)`
  is safe for the SPA — but VERIFY that before relying on it. `GET /api/v1/cards/{id}` and the
  write/move endpoints are unchanged.

API-FIRST (R4.1 / ADR 0005): this is a pure API slice — no required SPA change. Do NOT wire any
new UI; the params exist for the coming MCP/agent client. Only touch api.ts if a param genuinely
helps the SPA, and even then keep listCards() back-compatible.

TESTS (fold into the slice; integration lives under backend/tests/integration/, import app
modules inside test bodies per conftest.py):
- Each filter in isolation (column, epic_id, updated_since) returns the right subset.
- `updated_since` boundary (a card exactly at the timestamp — assert the chosen `>` vs `>=`).
- `limit` + `cursor` paging returns DISJOINT, gap-free pages that cover the full set; last page
  omits `X-Next-Cursor`.
- Combined filters AND correctly; empty result is a valid `[]` (no cursor).
- Bad inputs: unknown `column`, malformed `cursor`, out-of-range `limit` → 422 (or documented
  clamp).
- Back-compat: no params returns today's full list (keep/adapt the existing list assertions).
- Keep the whole suite green: backend pytest (unit + integration), frontend `npm run check` +
  `npm run build` + `npm run e2e`.

WORKFLOW (per CLAUDE.md — follow exactly):
1. `git switch main && git pull --ff-only` (ensure PR #13 is merged first), then
   `git switch -c feat/query-api`.
2. Install the pre-push hook if absent: `ln -sf ../../scripts/git-hooks/pre-push .git/hooks/pre-push`.
3. Local dev: `docker compose up -d db` (do NOT run the compose `app` service — it conflicts
   with the local uv backend on :8000; if it's up, `docker compose stop app`). Run
   `uv run alembic upgrade head` before starting the backend. Backend via `uv` from backend/;
   frontend via `npm` from frontend/. e2e via `npm run e2e` (needs the db + `npx playwright
   install chromium`).
4. Verify locally before the PR: ruff check + pytest (backend); npm run check + build + e2e
   (frontend) — all green. Confirm by hand with `curl`: each filter, a two-page `limit`+`cursor`
   walk reading `X-Next-Cursor`, `updated_since`, and that no-params still returns everything.
5. Update docs/milestone-2/SLICES.md's V3 status and CLAUDE.md's build/slice tables + the API
   row (note the new query params and that the body stays a bare array). If you drop `kind` and
   rename `parent_id`→`epic_id`, correct the stale param list in SHAPING.md / BREADBOARD.md too
   (or add a note), so the docs stop describing columns that don't exist.
6. Open a PR to main with a clear description. DO NOT self-merge — main is protected/PR-only.
   Match the repo's commit style (commits end with a Co-Authored-By trailer; PR bodies end with
   the "Generated with Claude Code" line).

Work in small, logical commits. If anything in the plan looks wrong once you're in the code, stop
and flag it rather than guessing.
```
