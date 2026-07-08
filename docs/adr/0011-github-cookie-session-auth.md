# ADR 0011 — Human login via GitHub OAuth + revocable cookie sessions

- **Status:** Accepted
- **Date:** 2026-07-08
- **Context source:** Milestone 3 (Accounts, Boards & Agent Access), requirements R1.1–R1.5;
  evolves the "no auth" stance of ADR 0007. Decisions D2/D3/D6 and the
  `docs/milestone-3/spike-fastapi-users-sync.md` spike. Delivered as slice **V6**.

## Context

ADR 0007 shipped the MVP with **no human authentication** — a single shared board, no accounts —
because the only interactive client was a trusted same-origin SPA. ADR 0010 later added an
**optional** bearer token on writes for non-interactive agents, but there was still no concept of a
*person*. Milestone 3 needs a first-class **User** identity (R1.4) that boards and (later) agent
tokens hang off, human login via **GitHub OAuth** (R1.1), a session that survives reloads and can be
logged out (R1.3), a **modular** provider setup so Google/email are config later, not rework (R1.2),
and a **landing page** for logged-out visitors (R1.5).

The hard constraint (ADR 0008): the app is deliberately **synchronous** (sync SQLAlchemy + psycopg
v3). The chosen library, **fastapi-users** (D2), has an **async-only** user store. The spike
(`spike-fastapi-users-sync.md`) resolved how the two coexist without a full-app rewrite.

## Decision

- **Adopt `fastapi-users` (15.x)** for the `User` + `OAuthAccount` models and the auth-backend /
  OAuth-client abstraction. User ids are **UUID**. Its tables are declarative mixins on the existing
  **shared `app.db.Base`**, so one Alembic pipeline covers board + auth tables (migration `0004`).
- **Two engines, one database (D6, spike-validated).** Keep the **sync** engine for all
  board/epic/card CRUD (and the future agent-token lookup) — ADR 0008 preserved. Add a **second,
  async** engine (`get_async_session`) used **only** by fastapi-users' login/session/OAuth store.
  Both point at the same `DATABASE_URL`; psycopg v3 serves sync and async, so the `+psycopg` URL is
  unchanged.
- **Humans authenticate via a GitHub OAuth cookie session (D3).** `httpx-oauth`'s `GitHubOAuth2` +
  fastapi-users' `get_oauth_router`; the auth backend is `CookieTransport` (httpOnly, `SameSite=Lax`,
  `Secure` in prod) + a **`DatabaseStrategy`** (a row per session in `access_token`). Logout deletes
  the row → **instant revocation**. (JWT-in-localStorage rejected: XSS-exposed, hard to revoke.)
- **Provider modularity (R1.2/A3)** falls out of the backend/OAuth-client config: adding Google or
  email/password later is another client + `include_router`, not a reshape. `/auth/login` (unused by
  OAuth users) stays mounted for exactly that future.
- **Graceful boot without credentials.** The GitHub OAuth routes register **only** when
  `GITHUB_OAUTH_CLIENT_ID`/`GITHUB_OAUTH_CLIENT_SECRET` are set. Without them the app still runs and
  the landing shows — login is simply unavailable. `AUTH_SECRET` signs session/state tokens;
  `COOKIE_SECURE` turns on `Secure` cookies in prod.
- **Auth routes are unversioned** (`/auth/*`, `/users/*`), like `/api/health` — session/identity
  plumbing, not versioned API resources. Single-origin serving is preserved (ADR 0003), so cookies
  are same-origin and there is **no new CORS surface** (R7.2). The Vite dev proxy forwards `/auth`
  and `/users` to the backend alongside `/api`.
- **Landing page (R1.5/A9).** A logged-out visitor sees `Landing.svelte` (hero + "Sign in with
  GitHub"); an authenticated one sees the board. The SPA picks which via `GET /users/me` (401 →
  landing). No client-side router — a conditional render, matching the existing `Board | Epics`
  toggle.

### Build-revealed detail (beyond the spike)

- **The authorize endpoint returns JSON, not a redirect.** fastapi-users' `/auth/github/authorize`
  responds `{ "authorization_url": … }`. So the landing CTA is not a bare link (as the mockup drew
  it) but a small fetch-then-`window.location` navigation (`startGitHubLogin` in `api.ts`).
- **Redirect back to the SPA after callback.** The stock cookie transport answers the OAuth callback
  with `204`, leaving the browser on a blank `/auth/github/callback` page. A thin
  `RedirectCookieTransport` overrides just the *login* response to `302 → /` (still setting the
  cookie), so the user lands on the app. Logout keeps the default `204`.

## Consequences

- **Positive:** a real User identity now exists for boards (V7) and agent tokens (V9) to reference;
  sessions are revocable; the async engine is quarantined to login only, so ADR 0008 holds for the
  whole board surface; the landing gives logged-out visitors a real front door.
- **Evolves ADR 0007.** "No auth" was an explicit MVP simplification; human accounts are the
  anticipated trigger. **Note the current gap:** `/api/v1` reads/writes are **not yet gated** on a
  user — V6 only adds *login*. Board **authorization** (a user may only touch their own boards)
  arrives in **V8**; until then the board API stays as open as before (ADR 0010's optional write
  token still applies and is untouched by this slice). Last-write-wins / no-real-time are unchanged.
- **Negative / deferred:** roles, board sharing, per-token scoping, and an audit trail remain Later
  (M3 D1). A production that never sets `AUTH_SECRET`/`COOKIE_SECURE` would run with an insecure dev
  secret and non-Secure cookies — acceptance for the milestone is that prod sets both as Fly secrets.
