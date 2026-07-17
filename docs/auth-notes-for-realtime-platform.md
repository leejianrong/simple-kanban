# Auth notes: same-origin cookie sessions on Fly (for a real-time platform)

> Answers to a question about how this repo (simple-kanban) handles auth, aimed at a
> FastAPI + SvelteKit + WebSocket platform on Fly that currently runs frontend and backend
> as two separate origins with a JWT-in-localStorage + Bearer setup.
>
> **Honesty caveat:** this repo has **no WebSocket surface**, so the WebSocket section (#4)
> is principled advice, not battle-tested code from here — it's flagged inline.

---

## The big realization: single origin ≠ nginx

This app is a single Fly app, single container, **single process**. There is no nginx.
`uvicorn` serves the built Svelte SPA as static files *and* the API, from one FastAPI app
(`backend/app/main.py`):

```python
app.include_router(boards.router, prefix="/api/v1")   # API first…
register_auth_routes(app)                              # …/auth, /users…
# …then, only if a built SPA exists, static assets + a catch-all fallback
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"))
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path):
        candidate = STATIC_DIR / full_path
        return FileResponse(candidate if candidate.is_file() else index_file)
```

The Svelte build is a multi-stage Docker step that copies `dist/` into the image; FastAPI reads
it via `STATIC_DIR`. Registration order matters — API and `/docs` are mounted before the catch-all
so they win; everything else falls through to `index.html` for client-side routing.

**Why this beats nginx for you:** nginx + uvicorn means two processes, a supervisor (s6/supervisord),
split logging, and a second thing that can crash — all to do something Starlette's `StaticFiles`
already does. The only reason to add nginx is aggressive static-asset caching/compression at scale,
and at "small scale, single always-on process" you explicitly don't need that. Same-origin is the
win you're after; a reverse proxy is an optional and separable second decision. Skip it.

Your SvelteKit is a static SPA (adapter-static), so this maps directly: build to `build/`,
`COPY` into the image, point `STATIC_DIR` at it. Deploy story stays trivially one `fly deploy`.

---

## 1 & 2 — Origin + the OAuth→SPA handoff (the JSON-page pain)

Same-origin. The JSON-body problem you hit is **specifically** because FastAPI-Users' OAuth router
inherits the transport's login response, and `BearerTransport` returns `{"access_token": …}` as JSON.
Switch the transport to a cookie and override *only* the login response to redirect. This repo's
`backend/app/users.py` does exactly that:

```python
class RedirectCookieTransport(CookieTransport):
    async def get_login_response(self, token: str) -> Response:
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        return self._set_login_cookie(response, token)   # cookie rides the 302

cookie_transport = RedirectCookieTransport(
    cookie_name="kanbanauth",
    cookie_max_age=SESSION_LIFETIME_SECONDS,   # 7 days
    cookie_secure=COOKIE_SECURE,               # False in dev, True in prod
    cookie_httponly=True,
    cookie_samesite="lax",
)
auth_backend = AuthenticationBackend(name="cookie", transport=cookie_transport,
                                     get_strategy=get_database_strategy)
```

So after GitHub bounces back to `/auth/github/callback`, the callback sets the HttpOnly cookie
**and** issues a `302 → /`. The browser lands on the app already authenticated. Logout keeps the
stock `204`. That single subclass is the whole fix for "browser lands on raw JSON."

**One gotcha the mockup missed:** FastAPI-Users' `/auth/github/authorize` *also* returns JSON
(`{"authorization_url": …}`), not a redirect. So the landing button isn't a plain `<a>` — it's a
tiny fetch-then-navigate:

```ts
const res = await fetch("/auth/github/authorize");
window.location.href = (await res.json()).authorization_url;
```

**Session strategy = `DatabaseStrategy`, not JWT.** A row per session in an `access_token` table;
logout deletes the row → **instant server-side revocation**. This is the deliberate anti-JWT choice
(a JWT in localStorage is XSS-exposed and can't be revoked before expiry). Worth copying —
revocability matters more than statelessness at your scale.

**SameSite / CSRF:** session cookie is `SameSite=Lax` (fine — the GitHub redirect is a top-level
navigation, which Lax permits; and it blocks cross-site POSTs). FastAPI-Users' OAuth router carries
its own **state CSRF cookie** during the handshake; this repo just matches its Secure flag to the
session's:

```python
fastapi_users.get_oauth_router(
    github_oauth_client, auth_backend, AUTH_SECRET,
    associate_by_email=True, is_verified_by_default=True,
    csrf_token_cookie_secure=COOKIE_SECURE,
)
```

**Local `http://localhost` dev (the Secure-cookie-dropped problem) is solved two ways at once:**

- `COOKIE_SECURE` is an env flag — **off** in dev (cookies work over http), **on** in prod (Fly secret).
  Same for the CSRF cookie.
- Dev reproduces same-origin via **Vite's proxy** so there's no CORS *and* no cross-origin cookie in
  dev either — `frontend/vite.config.ts`:
  ```ts
  server: { proxy: { "/api": "http://localhost:8000",
                     "/auth": "http://localhost:8000",
                     "/users": "http://localhost:8000" } }
  ```
  Everything is `localhost:5173` to the browser. (SvelteKit's dev server has the same `server.proxy`.)
  Don't forget to proxy `/auth` and `/users` too — they live *outside* `/api` because they're session
  plumbing, and it's an easy thing to miss.

**Behind Fly's TLS-terminating proxy**, the container sees `http` + `X-Forwarded-Proto: https`.
Without telling uvicorn to trust that, FastAPI-Users builds an `http://` `redirect_uri` and GitHub
rejects the mismatch. The `Dockerfile` CMD:

```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
```

`--proxy-headers --forwarded-allow-ips=*` is load-bearing for OAuth. Trusting all forwarded IPs is
safe *because only Fly's proxy can reach the internal port*. Also: a GitHub OAuth App allows exactly
**one** callback URL, so you need **two OAuth Apps** (localhost + prod).

---

## 3 — Two client types: one cookie backend + a hand-rolled PAT resolver

The part I'd most push you toward. **Do not run two FastAPI-Users auth backends** (cookie + Bearer)
and fight the library. This repo runs **one** cookie backend for humans, and a completely separate,
hand-rolled **personal-access-token** path for bots — then unifies them in a single dependency that
returns a `User` either way (`backend/app/authz.py`):

```python
def get_principal(
    user: User | None = Depends(current_optional_user),          # cookie session (async)
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if user is not None:
        return user                                              # human wins
    if credentials is not None:
        pat_user = _resolve_pat(db, credentials.credentials)     # else PAT bearer → owning User
        if pat_user is not None:
            return pat_user
    raise HTTPException(401, "authentication required",
                        headers={"WWW-Authenticate": "Bearer"})
```

Every route depends on `get_principal` and gets a real `User` — it never has to care *how* the caller
authenticated. Bots send `Authorization: Bearer kanban_pat_…`; browsers send the cookie automatically.

The PAT itself is **not** a FastAPI-Users JWT — it's a 256-bit random secret, shown once, stored only
as a hash (`backend/app/tokens.py`):

```python
TOKEN_PREFIX = "kanban_pat_"                    # greppable; secret-scanners can flag leaks
def hash_token(raw): return hmac.new(AUTH_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
def generate_token():
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:PREFIX_DISPLAY_LEN], hash_token(raw)        # persist prefix (display) + hash only
```

**Why HMAC-SHA256 and not bcrypt:** the token is high-entropy random, so you don't need per-row
salting to slow brute force — and a deterministic hash means auth is a single indexed
`WHERE token_hash = :h` lookup instead of an O(n) scan. Keying it with a server-side pepper
(`AUTH_SECRET`) means a stolen DB alone can't verify guessed tokens offline. Revocation = delete the
row. Lookup also stamps `last_used_at`.

**FastAPI-Users gotchas doing this:**

- FastAPI-Users' store is **async-only**, but this app's board CRUD is deliberately **sync**. The
  trick: a sync endpoint can still `Depends()` on the async `current_optional_user` — FastAPI resolves
  the async sub-dependency fine. So the cookie half runs async, the PAT half runs sync, both compose
  in one sync route.
- Use `current_user(..., optional=True)` for the resolver so a missing cookie yields `None` instead
  of a premature 401 — you want to *fall through* to the PAT branch, then decide.
- Precedence matters: cookie first. A browser that also happens to send a stale bearer shouldn't get
  downgraded.

---

## 4 — WebSocket auth (⚠️ NOT implemented in this repo — principled advice)

This repo has no WS, so treat this as reasoning from the architecture, not shipped code. But
same-origin cookies make WS auth *dramatically* simpler, which is a strong reason to go same-origin
regardless:

- **The WS handshake is an ordinary HTTP GET Upgrade**, so a same-origin HttpOnly cookie is sent
  automatically. You authenticate the connection at accept time with the *same* session lookup as
  HTTP — no token in the URL, no token in a subprotocol, nothing exposed to JS:
  ```python
  @app.websocket("/ws")
  async def ws(websocket: WebSocket, session=Depends(get_async_session)):
      user = await resolve_user_from_cookie(websocket.cookies.get("kanbanauth"), session)
      if user is None:
          await websocket.close(code=1008); return
      await websocket.accept()
  ```
  Cross-origin, you *can't* do this cleanly — browsers don't let you set WS headers, so people
  smuggle JWTs through `Sec-WebSocket-Protocol` or query strings (which land in logs). Same-origin
  cookie sidesteps the whole mess. **This is arguably the single biggest reason to collapse origins
  for your bot-facing platform.**
- **Bot clients** (non-browser) authenticate the WS with a header:
  `Authorization: Bearer kanban_pat_…` on the handshake, resolved by the same PAT path. Non-browser
  clients *can* set handshake headers, so this is clean.
- **Fly proxy passes `Upgrade`/`Connection` and long-lived sockets natively** — no special config; it
  speaks WS. The realistic surprises are: (a) **idle timeout** — send app-level pings (or WS ping
  frames) every ~30–50s so an idle socket isn't reaped; (b) **health checks** — point Fly's
  `[[http_service.checks]]` at a plain `GET /api/health`, *not* the WS path; (c) with authoritative
  in-memory state, set `[http_service] concurrency` generously and don't let autoscaling spin a second
  machine.

---

## 5 — Security posture

- **Token lives in an HttpOnly cookie, never localStorage.** XSS can't read it. That's the deliberate
  trade vs. JWT-in-localStorage (rejected in ADR 0011 as XSS-exposed and hard to revoke).
- **XSS:** HttpOnly neutralizes token theft; rely on Svelte's default escaping and avoid `{@html}` on
  untrusted input.
- **CSRF:** `SameSite=Lax` blocks cross-site form/POST forgery; the OAuth handshake has its own state
  CSRF cookie. At your scale Lax is sufficient — if you ever need cross-site embedding you'd move to
  `SameSite=None; Secure` + an explicit CSRF token, but don't pre-pay that.
- **Lifetime/refresh:** 7-day DB-backed sessions, **no refresh token** — expiry just means log in
  again. Server-side rows mean logout and admin revocation are instant. Simple and secure; refresh
  tokens are complexity you don't need here.
- **Pepper coupling:** `AUTH_SECRET` signs sessions *and* peppers PAT hashes, so rotating it
  invalidates all sessions and PATs at once — a feature (one kill switch), but know it.

---

## 6 — If I were starting over on Fly (config sketch)

Honestly this repo's layout *is* what I'd do — with **one critical change for your constraint**: this
app scales to zero, but yours **can't** (authoritative in-memory state). So flip the machine policy:

```toml
# fly.toml — adapted for a single always-on, non-scalable process
app = "your-app"
primary_region = "iad"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "off"      # ← you CANNOT scale to zero: in-memory state
  auto_start_machines = false     # ← never let Fly spin a 2nd machine
  min_machines_running = 1        # ← exactly one, always on

  [http_service.concurrency]
    type = "connections"          # WS-friendly: count sockets, not requests
    hard_limit = 400
    soft_limit = 350

  [[http_service.checks]]
    path = "/api/health"          # plain HTTP, never the WS path
    interval = "15s"
    timeout = "2s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"                # bump from 256mb if you hold game state in RAM
```

```dockerfile
# Multi-stage: build the static SPA, serve it + API from ONE uvicorn process (no nginx)
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # adapter-static → /frontend/build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV STATIC_DIR=/app/static PATH="/app/.venv/bin:$PATH"
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=frontend /frontend/build ./static
EXPOSE 8000
# --proxy-headers + --forwarded-allow-ips=* → correct https redirect_uri for OAuth
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
```

**The one thing I'd *not* copy for you:** this app runs uvicorn single-process because its state is
all in Postgres, so it could scale horizontally if it wanted. Yours holds authoritative state in
memory — so **stay single-process, single-machine, and make that explicit in fly.toml** as above, and
never add `--workers > 1` (multiple workers = multiple divergent in-memory game states in one machine,
same bug as horizontal scaling).

---

## Migration path from where you are (order of payoff)

1. Collapse to one Fly app: build SPA → `COPY` into the backend image → serve via `StaticFiles` +
   SPA fallback. Kills CORS. *(No nginx.)*
2. Swap `BearerTransport` → `CookieTransport` + a `RedirectCookieTransport` subclass. Kills the
   JSON-handoff ugliness and moves the token out of localStorage.
3. Switch the session strategy to `DatabaseStrategy` for revocable logout.
4. Add a hand-rolled PAT table + a `get_principal` dependency that tries cookie then Bearer, for your
   bots.
5. Authenticate WS from the same cookie (browsers) / bearer (bots) at accept time.
