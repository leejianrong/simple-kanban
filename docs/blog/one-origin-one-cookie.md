<!--
title: "One origin, one cookie: how GitHub login works here"
description: How a FastAPI + Svelte app authenticates humans with a same-origin HttpOnly cookie session minted through GitHub OAuth, and what has to change when the frontend and backend split across origins and CORS shows up.
slug: one-origin-one-cookie
author: Jian
date: 2026-07-11
status: Draft
tags: [auth, oauth, fastapi, svelte, cookies, cors, fly-io]
-->

---

# One origin, one cookie: how GitHub login works here

Most of the auth advice you find online assumes your frontend and backend live at
different addresses, so it spends its energy on tokens, CORS headers, and refresh
flows. Simple Kanban doesn't have that problem, because the frontend and backend are
the same thing: one FastAPI process that serves the built Svelte files and the API
from a single origin. That one fact makes the whole auth story shorter, and it's
worth walking through why, because the day you *do* split the origins, every piece of
this has to change.

## The cast

Login is a short conversation between five parties, and it helps to hold all five in
your head before reading any code.

The **browser** stores cookies, follows redirects, and enforces the same-origin
policy. The **SPA** is the built Svelte bundle running inside that browser; it's just
static files the browser downloaded, and it holds no secrets of its own. **FastAPI**
is one uvicorn process serving the SPA's files, the API, and the auth routes all
together. **GitHub** is the OAuth provider that vouches for who the user is, and it
never sees our database. **Postgres** stores the user row, the linked OAuth account,
and one session row per active login.

The load-bearing detail is that the SPA and the API share one origin: same scheme,
host, and port, like `https://simple-kanban-jian.fly.dev`. In production FastAPI
serves the Svelte files itself with a catch-all fallback, and in development Vite
proxies `/api`, `/auth`, and `/users` to the backend, so the browser sees one origin
either way. Because of that, the browser attaches the session cookie to every request
without being asked, and CORS never enters the picture at all.

## Why a cookie and not a token

The design most tutorials reach for is a JSON Web Token: you log in, get a JWT back as
JSON, stash it in `localStorage`, and send it as an `Authorization: Bearer` header. We
deliberately don't do that for human sessions, and I'd argue most small apps
shouldn't either.

Two reasons. Anything in `localStorage` is readable by any JavaScript on the page, so
one bad dependency or one injected script and the token walks out the door. An
`HttpOnly` cookie is invisible to JavaScript, so `document.cookie` can't see it and
neither can an attacker's script. The other reason is revocation: a stateless JWT
stays valid until it expires, and you can't truly log someone out before then. We
store a session row per login instead, so logging out deletes the row and the session
is dead immediately.

The cost is a database lookup on each request rather than stateless verification. At
this scale that's invisible, and being able to revoke a session and survive an XSS bug
is worth far more than saving one indexed query. Bots and CLIs, which can't hold a
cookie session cleanly, get their own token mechanism, which I'll come back to.

## The login flow, start to finish

Here's the whole round trip, from a logged-out visitor clicking a button to landing
back on the board with a live session.

It starts with the browser loading the app. FastAPI's catch-all returns `index.html`,
the Svelte bundle boots, and on mount the SPA asks the backend who it's talking to:

```python
# frontend/src/lib/api.ts
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const res = await fetch("/users/me");   // same-origin, so the cookie rides along
  if (res.status === 401) return null;    // not logged in -> show the landing page
  return res.json();                      // logged in -> the user object
}
```

With no session cookie yet, fastapi-users answers `401`, the SPA reads that as "logged
out", and it shows the landing page instead of the board.

When the user clicks "Sign in with GitHub", the button doesn't link straight to
GitHub. fastapi-users' authorize endpoint hands back the GitHub URL as JSON rather
than a redirect (a detail that surprised me the first time), so the SPA fetches it and
then navigates the browser there:

```js
export async function startGitHubLogin() {
  const res = await fetch("/auth/github/authorize");
  const { authorization_url } = await res.json();   // JSON, not a redirect
  window.location.href = authorization_url;          // now the browser leaves for github.com
}
```

That same response quietly sets a short-lived state cookie, which is an anti-CSRF
nonce for the handshake we're about to do.

Now the browser is on `github.com`. The user logs in if they need to and approves the
app, and this is the only moment a GitHub password is ever involved (it never touches
our servers). GitHub then redirects back to the one callback URL registered for the
OAuth App, carrying a temporary `code` and the `state` nonce:

```
GitHub -> Browser:  302 -> /auth/github/callback?code=...&state=...
```

The callback is where the interesting server-side work happens, all inside
fastapi-users' OAuth router. It verifies the `state` against the state cookie to
reject a forged callback, exchanges the `code` for a GitHub access token
server-to-server (the browser never sees this), then fetches the profile and email and
finds-or-creates a user. Because it's configured with `associate_by_email=True`, a
returning user is matched by email rather than duplicated.

Then it mints the session. The `DatabaseStrategy` writes a new row to the
`access_token` table (that row *is* the session), and a small custom transport sets
the cookie and redirects to `/` in one response:

```python
# backend/app/users.py
# The stock cookie transport answers the OAuth callback with 204 No Content, which
# strands the browser on a blank /auth/github/callback page. We override only the
# login response to redirect to the SPA root; the cookie still rides along.
class RedirectCookieTransport(CookieTransport):
    async def get_login_response(self, token: str) -> Response:
        response = RedirectResponse(url="/", status_code=302)
        return self._set_login_cookie(response, token)   # Set-Cookie on the 302

cookie_transport = RedirectCookieTransport(
    cookie_name="kanbanauth",
    cookie_max_age=SESSION_LIFETIME_SECONDS,  # 7 days
    cookie_secure=COOKIE_SECURE,              # True in prod, False on http://localhost
    cookie_httponly=True,                     # invisible to JavaScript
    cookie_samesite="lax",                    # CSRF defence, covered below
)
```

That override is the whole fix for the classic bug where the browser lands on a blank
page of raw JSON after login. The browser follows the `302` to `/`, the SPA reloads
and repeats its "who am I?" check, and this time the `kanbanauth` cookie comes with
it, so `/users/me` returns `200` and the gate flips to the board.

A neat way to read the flow is as three separate secrets doing three separate jobs. A
temporary state cookie secures the GitHub handshake, the durable `kanbanauth` cookie
proves identity afterwards, and the `code` from GitHub isn't a cookie at all: it's a
one-time voucher the backend redeems server-side so no real secret ever reaches the
browser.

## What's actually in the cookie

This is the `Set-Cookie` header the browser gets on login:

```
Set-Cookie: kanbanauth=<opaque-session-id>; Max-Age=604800; Path=/;
            HttpOnly; SameSite=Lax; Secure
```

Every attribute is a decision. The value is opaque, not a JWT, so on its own it means
nothing: it's a lookup key into the `access_token` table. `HttpOnly` keeps JavaScript
from reading it, which is the property that makes XSS unable to steal a session.
`SameSite=Lax` tells the browser to send the cookie on top-level navigations to our
site (so the redirect back from GitHub works) but to withhold it from cross-site
background requests (so another site can't quietly POST to our API using your cookie).
That last one is our built-in CSRF defence, and it's free as long as we stay
same-origin. `Secure` limits the cookie to HTTPS, which we turn on in production and
off in local development, since `http://localhost` would otherwise drop it. The
seven-day `Max-Age` is a plain expiry with no refresh token behind it; when it lapses,
you log in again.

## Staying logged in, and logging out

Every request after login is same-origin, so the browser attaches `kanbanauth` with no
help from the SPA. On the backend one dependency turns that cookie into the current
user (or a `401`), and then checks the user owns the board they're touching (or a
`403`). Bots take a different door into the same room: they send a personal access
token as a bearer credential, and the same dependency resolves either a cookie or a
token down to the same `User`, so routes never care which was used. The token is a
256-bit random secret shown once and stored only as an HMAC-SHA256 hash, which means
authentication is a single indexed lookup and a stolen database alone can't be used to
guess tokens offline.

Logout is one POST, and because the session is a real row, deleting it is genuine
revocation rather than "wait for the token to expire":

```
Browser -> POST /auth/logout                                   (cookie sent automatically)
FastAPI -> DELETE FROM access_token WHERE token = <id>         (the row is gone)
FastAPI -> Set-Cookie: kanbanauth=; Max-Age=0                  (the cookie is cleared)
        <- 204 No Content   ->  the SPA drops back to the landing page
```

## Two environments, two small surprises

The same code runs locally and in production, and two environment details are what let
it work in both.

A `Secure` cookie is dropped by the browser over plain `http://localhost`, so
`COOKIE_SECURE` is an environment flag: off in development, on in production as a Fly
secret. Development sidesteps cross-origin trouble entirely by having Vite proxy
`/api`, `/auth`, and `/users` to the backend, so the browser sees a single
`localhost:5173` origin that mirrors production.

The second surprise is HTTPS behind Fly's proxy. Fly terminates TLS at its edge, so
the container receives plain `http` with an `X-Forwarded-Proto: https` header. Left
alone, fastapi-users builds an `http://` callback `redirect_uri`, and GitHub rejects
it for not matching the registered `https://` URL. One flag pair on uvicorn fixes it:

```dockerfile
# Dockerfile CMD
uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips=*   # trust Fly's X-Forwarded-Proto
```

One more thing to know: a GitHub OAuth App allows exactly one callback URL, so
development and production need two separate OAuth Apps, one pointing at localhost and
one at the production host.

## The day you split the origins

Everything above is short *because* there's one origin. The moment the frontend and
backend move to different origins (two Fly apps, two containers, or two Kubernetes
services on different hostnames) three things break at once, so it's worth knowing what
you're signing up for.

First, the browser blocks the request. A `fetch()` from `app.example.com` to
`api.example.com` is cross-origin, and the browser won't hand the response back unless
the API opts in with CORS headers. Because we send a cookie, the rules tighten: you
can't use the `*` wildcard origin, you have to echo the exact origin plus
`Allow-Credentials: true`, and anything beyond a simple GET triggers an `OPTIONS`
preflight the server has to answer.

```python
# backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],  # exact origin, never "*" with credentials
    allow_credentials=True,                      # let the browser send/receive the cookie
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Second, the cookie stops being sent. A `SameSite=Lax` cookie isn't attached to
cross-site background requests, which is now every API call, so you have to weaken it
to `SameSite=None`, which the spec then requires to also be `Secure` (HTTPS
everywhere, including local development). The SPA also has to opt in per request with
`credentials: "include"`. And here's the trap that catches people: when the page is
`app.example.com` and the cookie belongs to `api.example.com`, browsers treat it as a
third-party cookie, which Safari blocks outright and Chrome is phasing out. A
`SameSite=None` cookie shared across two unrelated domains is fragile, and I wouldn't
build anything important on it.

Third, the OAuth redirect no longer lands the cookie where it's needed. The callback
runs on `api.example.com` and sets the cookie there, but the redirect sends the browser
to `app.example.com`, which can't see it. There are two ways out. The good one is to
put both on sibling subdomains of a shared domain and set the cookie's
`Domain=.example.com`, which makes it a first-party cookie both subdomains share, so
`SameSite=Lax` keeps working and third-party blocking doesn't apply (fastapi-users'
`CookieTransport` takes a `cookie_domain` for exactly this). You still need CORS,
because the subdomains are still different origins, but the cookie stays healthy. The
worse way, for genuinely unrelated domains, is to redirect to the SPA with a one-time
code in the URL fragment and have the SPA exchange it for a session. That's usually
the point where teams give up on cookies and switch to bearer tokens, which quietly
hands back the XSS exposure we started out avoiding.

One more consequence: once the cookie travels cross-site with `SameSite=None`, the
free CSRF protection from `Lax` is gone, and you need an explicit defence like a
double-submit token.

## The escape hatch worth reaching for first

Here's the insight that saves most of that pain: separate containers don't have to
mean separate origins. Put a reverse proxy in front of both services on one hostname
and route by path, with `/` going to the frontend and `/api` and `/auth` going to the
backend, and the browser sees one origin again. You keep `SameSite=Lax`, you keep the
`HttpOnly` cookie, and you delete all the CORS code. It's the same job FastAPI does
today by serving the static files itself, just moved to a dedicated layer so the two
apps can deploy and scale on their own.

```nginx
server {
  listen 443 ssl;
  server_name app.example.com;               # one hostname the browser talks to

  location /api/   { proxy_pass http://backend:8000; }   # FastAPI
  location /auth/  { proxy_pass http://backend:8000; }   # FastAPI (OAuth routes)
  location /users/ { proxy_pass http://backend:8000; }

  location /ws {                               # WebSocket upgrade
    proxy_pass http://backend:8000;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;                  # keep long-lived sockets alive
  }

  location / { proxy_pass http://frontend:80; }          # the static SPA, everything else
}
```

The Kubernetes version is the same idea expressed as an Ingress: one `host`, several
`paths`, `/api` and `/auth` to the backend service and `/` to the frontend service. A
single host means a single origin, which means no CORS.

So if I had to sum up the preference order, it's this. Stay on one origin if you can,
whether that's FastAPI serving the SPA or a proxy path-routing to both, because it
needs no CORS and keeps the cookie CSRF-safe by default. If you can't, put the two on
sibling subdomains of a shared domain with a parent-domain cookie, which keeps the
cookie story healthy and only adds a CORS allow-list. Reach for `SameSite=None` cookies
across unrelated domains, or for bearer tokens in the browser, only when nothing else
is available, because that's where the security footguns live. The whole point of the
setup we have is that it stays boring, and boring is a feature.
