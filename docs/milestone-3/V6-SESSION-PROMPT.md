# V6 session prompt — Human login (GitHub OAuth) + landing page

Copy the block below into a **new** chat session to build Milestone 3 slice **V6 (human login via
GitHub OAuth + the logged-out landing page)** — the foundation slice of Milestone 3.

**Before running it:**
- Milestone 2 (V1–V5) is fully merged; just start from a fresh `main`.
- V6 needs a **GitHub OAuth App** (manual, one-time): register one at github.com → Settings →
  Developer settings → OAuth Apps; note the Client ID + secret; set the callback to your local
  auth callback URL. The building session will tell you the exact callback path once wired. The
  app must still boot/test **without** these creds (login simply unavailable) so CI and credless
  dev aren't blocked.

---

```
You're picking up an in-progress project on disk: `simple-kanban`, a deployed kanban app (FastAPI +
sync SQLAlchemy/psycopg on Postgres, Svelte 5 + Vite SPA, single artifact; a stdio MCP server in
`mcp/`). Milestones 1 and 2 are complete and merged: full board CRUD + drag, epics, versioned
`/api/v1`, a query API, optional bearer-token auth on writes, and an MCP server. **Milestone 3
(Accounts, Boards & Agent Access)** is fully shaped but not yet built. Build its FIRST slice, V6,
following the same slice-behind-a-PR cadence as M1/M2.

READ THESE FIRST — they are authoritative:
- CLAUDE.md — repo conventions (branch/PR workflow, commands, architecture, ADRs). Follow exactly.
- docs/milestone-3/SHAPING.md — requirements (R0–R8), decisions D1–D6, Shape A (parts A1–A9).
- docs/milestone-3/spike-fastapi-users-sync.md — THE technical guide for the auth foundation; its
  findings were verified empirically. Follow the "resolved architecture" section.
- docs/milestone-3/SLICES.md (§ V6) and BREADBOARD.md (Places S1/S2/S3, wiring).
- docs/milestone-3/landing-mockup.html — the approved visual mockup; build Landing.svelte from it.
- docs/adr/0007 (no-auth/LWW) and 0008 (sync SQLAlchemy + psycopg v3) — V6 evolves 0007.
- Current backend/app/ (main.py, db.py, models.py, routers/) and frontend/src/ (App.svelte,
  lib/api.ts, lib/board.svelte.ts, app.css).

IMPORTANT — verify against the code, don't trust docs blindly. The shaping docs describe intent; the
spike was run in a throwaway env, so re-confirm package versions and APIs when you install. This
slice introduces a NEW dependency (fastapi-users) and a SECOND, async database engine alongside the
existing sync one — a significant architectural change. Follow the spike's resolved architecture:
ONE shared `app.db.Base` (one Alembic pipeline), a sync engine for all board/card/epic CRUD
(unchanged, ADR 0008 preserved), and a new ASYNC engine used ONLY by fastapi-users' human login.

SCOPE — build V6 ONLY: human login via GitHub OAuth + the landing page + auth-gated SPA routing.
Do NOT build V7–V10 (boards, board authorization, agent tokens, MCP scoping) — later slices. In
particular: no board model yet, no per-board scoping, and DO NOT touch the existing V4 `API_TOKENS`
write-guard or the MCP server in this slice.

WHAT V6 IS (Shape A parts A1 + A2 + A3 + A9; per SLICES.md § V6 and the spike):
- Backend — auth foundation (A1):
  - Add deps to backend/pyproject.toml: `fastapi-users[sqlalchemy]`, `fastapi-users[oauth]`
    (brings httpx-oauth), and the SQLAlchemy async extra / `greenlet` needed for the async engine.
    Keep psycopg v3 (it supports async). Re-run `uv lock`/`uv sync`.
  - Add fastapi-users `User` + `OAuthAccount` (+ the `access_token` table for the DB session
    strategy) as declarative mixins on the EXISTING `app.db.Base` (User id = UUID). Add a second
    async engine + `get_async_session()` in db.py; leave the sync engine + `get_db()` untouched.
  - Alembic migration creating `user` / `oauth_account` / `access_token`. Autogenerate sees them via
    the one shared Base (import the models in alembic/env.py).
- Backend — login (A2) + provider modularity (A3):
  - GitHub OAuth via httpx-oauth `GitHubOAuth2` + fastapi-users `get_oauth_router`; a users router
    (`/users/me`, logout). Auth backend = `CookieTransport` (httpOnly, SameSite=Lax, Secure in prod)
    + `DatabaseStrategy` (revocable — logout deletes the access-token row). Keep the OAuth-client /
    backend registration modular so adding Google/email later is config, not rework (A3).
  - Boot WITHOUT GitHub creds gracefully: only register the OAuth routes when
    GITHUB_OAUTH_CLIENT_ID/SECRET are set; otherwise the app runs and the landing shows (login just
    unavailable). Add a session/token secret env var. Document all new env vars in CLAUDE.md.
  - Resolve the dev wiring: `/auth/*` must be reachable from the browser during local dev — extend
    the Vite proxy to forward `/auth` (and `/users`) to :8000, or navigate straight to the backend.
    Work out the exact callback URL and put it in the setup docs + the GitHub OAuth App.
- Frontend — landing + routing (A9):
  - `Landing.svelte` built from docs/milestone-3/landing-mockup.html, refactored into Svelte + the
    app's app.css tokens (don't inline the whole mockup; reuse existing styles; keep light/dark).
    The "Sign in with GitHub" button links to the backend authorize route.
  - App shell: on load, call `GET /users/me`; 401 → render Landing; authenticated → render the
    existing board app. Add the current user + a Log out control to the top bar. Add
    `getCurrentUser()` / `logout()` to lib/api.ts. No client-side router needed (conditional render,
    matching the existing Board|Epics toggle style).

TESTS (fold into the slice):
- Backend integration (tests/integration): unauthenticated `GET /users/me` → 401; the OAuth callback
  creates a User + OAuthAccount and sets a session cookie; an authenticated request is recognized;
  logout revokes the session. MOCK the GitHub token exchange / userinfo (no real network). The async
  auth store needs an async test setup — add it without disturbing the existing sync `client`/DB
  fixtures in tests/integration/conftest.py.
- Frontend: `npm run check` + `npm run build`; Playwright e2e — logged-out shows the landing;
  a stubbed/mocked login lands on the board and survives reload; logout returns to the landing
  (stub the auth endpoints via `page.route`, consistent with the existing e2e style).
- Keep the whole suite green: backend ruff + pytest (unit + integration), mcp job, frontend
  check/build/e2e.

DOCS (fold in):
- Write a new ADR evolving ADR 0007 (no-auth → optional GitHub cookie sessions; reads/writes still
  open where not yet gated — board authorization arrives in V8). Update the ADR index in CLAUDE.md.
- Update CLAUDE.md (built/slice tables, new env vars, the async-engine note) and mark V6 built in
  docs/milestone-3/SLICES.md. Keep the shaping docs consistent (ripple changes up if the build
  reveals something different from the plan — flag it, don't silently diverge).

WORKFLOW (per CLAUDE.md — follow exactly):
1. `git switch main && git pull --ff-only`, then `git switch -c feat/github-login`.
2. Install the pre-push hook if absent: `ln -sf ../../scripts/git-hooks/pre-push .git/hooks/pre-push`.
3. Local dev: `docker compose up -d db` (NOT the compose `app` service — it conflicts on :8000;
   `docker compose stop app` if it's up). `uv run alembic upgrade head` before starting the backend.
   Backend via `uv` from backend/; frontend via `npm` from frontend/. e2e via `npm run e2e`.
4. Verify locally before the PR: ruff + pytest (backend), mcp tests, npm run check + build + e2e —
   all green. Confirm by hand: logged out shows the landing at :5173; with a real GitHub OAuth App
   configured, Sign in → GitHub → back to the board; reload stays in; logout → landing.
5. Open a PR to main with a clear description. DO NOT self-merge — main is protected/PR-only. Match
   the repo's commit style (Co-Authored-By trailer; PR body ends with the "Generated with Claude
   Code" line).

This is a large foundation slice. Work in small, logical commits (e.g. auth models + async engine +
migration; OAuth/session backend + routes; landing + routing + logout; docs/ADR). If the sync/async
integration or the OAuth wiring fights the plan, STOP and flag it rather than guessing — the spike
is your reference for the intended approach.
```
