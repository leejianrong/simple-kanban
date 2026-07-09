You're picking up an in-progress project on disk: `simple-kanban`, a deployed kanban app
(FastAPI + sync SQLAlchemy/psycopg on Postgres, Svelte 5 + Vite SPA served as a single artifact;
a stdio MCP server in `mcp/`). Milestones 1 and 2 are complete and merged. **Milestone 3
(Accounts, Boards & Agent Access)** is fully shaped and partly built:

- **V6 (merged, ADR 0011):** human GitHub OAuth login + revocable cookie session (fastapi-users on
  a SECOND, async engine beside the sync one), a landing page, and auth-gated SPA routing.
- **V7 (merged, ADR 0012):** multi-board with ownership — a first-class `board` table
  (`name` + nullable `owner_id`→user), NOT NULL `board_id` on `card`+`epic` (ON DELETE CASCADE),
  `/api/v1/boards` CRUD, a top-bar board switcher, and a migration that backfilled all existing
  cards/epics into one UNCLAIMED default board (owner_id NULL). Positions are per (board, column).

Build the NEXT slice, **V8 (Board authorization)**, following the same slice-behind-a-PR cadence.

READ THESE FIRST — they are authoritative:
- CLAUDE.md — repo conventions (branch/PR workflow, commands, architecture, ADRs). Follow exactly.
- docs/milestone-3/SHAPING.md (requirements R3.1/R3.4, decisions D3/D5/D6, Shape part **A5**),
  SLICES.md (**§ V8**), BREADBOARD.md (Place **S5**, the "principal resolver" + "board-authorization
  dependency" rows).
- docs/adr/0011 (cookie sessions) and 0012 (multi-board + ownership) — V8 builds directly on both.
- Current code: backend/app/users.py (`current_active_user`, `current_optional_user`),
  backend/app/routers/{boards,cards,epics}.py, backend/app/auth.py (V4 `API_TOKENS` write-guard),
  backend/tests/integration/conftest.py (note the `logged_in_client` + `mock_github` fixtures and
  the per-test reset that recreates a default board), frontend/src/lib/{api.ts,board.svelte.ts}.

IMPORTANT — verify against the code, don't trust docs blindly. Re-confirm current behavior before
changing it.

WHAT V8 IS (Shape A part A5; SLICES § V8):
- A single **board-authorization** dependency (sync): given the resolved principal + a target board,
  allow iff the principal owns the board, else **403**. Applied to every board-scoped read/write:
  cards (list/get/create/patch/delete/move), epics (same), and board detail/patch/delete.
- List endpoints return **only the principal's** boards/cards/epics (GET /boards, GET /cards,
  GET /epics scoped to the caller).
- This makes **`/api/v1` auth-required** — a deliberate, documented contract change (R3.4). It stays
  under `/api/v1` because we own all clients and move them together (R6.2). Unauthenticated →
  **401**; authenticated non-owner → **403**.

KEY DECISIONS TO CONFIRM WITH THE USER BEFORE BUILDING (these are real forks — ask, with a
recommendation, like the V7 kickoff did):
1. **The unclaimed default board.** V7's migration left it with owner_id NULL, so after V8 it would
   be invisible to everyone (nobody owns it), hiding the migrated production data. Decide how it gets
   claimed — e.g. first authenticated user adopts all unclaimed boards / an explicit "claim" action /
   leave orphaned. (Recommend: the first logged-in user claims unclaimed boards, so prod data isn't
   stranded.)
2. **Agents / the MCP server during the V8→V9 window.** V8's principal is the **human cookie
   session** only; per-user agent PATs are **V9**, and MCP board-scoping is **V10**. But V8 makes
   `/api/v1` auth-required, which would break the MCP server (it uses the V4 `API_TOKENS` bearer,
   which is NOT tied to a user and can't pass an owner check). Decide the transitional behavior —
   e.g. keep `API_TOKENS` as a temporary unscoped service bypass until V9 retires it / accept MCP
   can't write until V9 and dogfood via the SPA. Do NOT silently break MCP. (BREADBOARD S5 envisions
   the resolver accepting "cookie session OR bearer PAT → User", but the PAT half is V9.)
3. **Cross-board epic links / the epic selector** — confirm nothing lets a story link an epic on
   another user's board once lists are scoped.

⚠️ THE BIGGEST PRACTICAL HURDLE IS THE TESTS — plan for it up front:
- **Backend integration:** almost every existing test hits `/api/v1` with NO auth (open). Once V8
  requires a session, they'll all 401. You'll need to route board-scoped tests through an
  authenticated, board-owning principal. The `logged_in_client` fixture already exists in
  tests/integration/conftest.py (V7) — lean on it; likely make card/epic tests create + own their
  board. This is a substantial fixture refactor; do it carefully and keep the import-order guard
  happy (app imports stay INSIDE test bodies — see conftest's `pytest_collection_finish`).
- **e2e (Playwright):** specs currently stub `GET /users/me` via `page.route` (a fake user) but hit
  the REAL backend for `/api/v1`. With V8 the real backend needs a real session cookie for
  `/api/v1`, which a route-stub can't create. Decide an approach (a test-only login/seed path, or a
  real session established against the backend) — this needs real thought, not a stub. Flag it early
  if it fights the plan.
- Keep the whole suite green: backend ruff + pytest (unit + integration), the `mcp` job, frontend
  check/build/e2e.

TECHNICAL NOTES you'll want (learned building V6/V7):
- Two engines, one DB: SYNC engine for all board/card/epic CRUD (ADR 0008) + an ASYNC engine used
  ONLY by fastapi-users. The board routes are sync but can depend on the async `current_active_user`
  / `current_optional_user` — FastAPI resolves async deps for sync endpoints (proven in V7's board
  create). Use that to resolve the human principal in the sync authz dependency.
- Principal is a `User` (UUID id). `board.owner_id` is nullable. `resolve_board_id()` lives in
  routers/boards.py. `current_optional_user` (no 401) and `current_active_user` (401) are in users.py.
- Per-test reset recreates a default board (id=1); tests that assume "board 1 exists" rely on it.

TESTS (fold into the slice): integration — owner allowed on read/write/move/delete; non-owner →
403; list endpoints omit others' data; unauthenticated → 401. e2e — a second logged-in user cannot
see the first's board. Acceptance: the isolation demo (A can't touch B) holds across API + UI.

DOCS (fold in): write a new ADR (0013) for board authorization / `/api/v1` becoming auth-required
(it realizes D3's "one authorization layer" and the V8 contract change flagged in SLICES). Update
CLAUDE.md (built/slice tables — the "not yet owner-gated" caveats become "owner-gated"; conventions;
ADR index) and mark V8 built in docs/milestone-3/SLICES.md. Ripple any doc that currently says
`/api/v1` is open.

WORKFLOW (per CLAUDE.md — follow exactly):
1. `git switch main && git pull --ff-only`, then `git switch -c feat/board-authz`.
2. Pre-push hook should already be installed (symlinked in .git/hooks). If not:
   `ln -sf ../../scripts/git-hooks/pre-push .git/hooks/pre-push`.
3. Local dev: `docker compose up -d db`; `uv run alembic upgrade head` before starting the backend.
   Backend via `uv` from backend/; frontend via `npm` from frontend/; e2e via `npm run e2e`.
4. Verify locally before the PR: ruff + pytest (backend), mcp tests, npm run check + build + e2e —
   all green. Confirm by hand: two users, each sees only their own boards; A gets 403 on B's board.
5. Work in small, logical commits (authz dependency + principal wiring; list scoping; test refactor;
   frontend; docs/ADR). Open a PR to main with a clear description. DO NOT self-merge — main is
   protected/PR-only. Match the repo's commit style (end commits with
   `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; end the PR body with the
   "Generated with Claude Code" line).

This slice is smaller in new code than V6/V7 but higher-risk because it flips `/api/v1` from open to
auth-required and forces a test-harness rework. If the principal/authz wiring or the e2e auth story
fights the plan, STOP and flag it rather than guessing.
