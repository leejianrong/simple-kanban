# ADR 0017 — Observability: DB-readiness health, structured logging, error tracking

- **Status:** Accepted
- **Date:** 2026-07-13
- **Context source:** Card **KAN-172** (Observability: DB-probe health check, structured request
  logging, error tracking). Operational hardening for the deployed app (ADR 0004 hosting), building
  on the two-engine split (ADR 0008 sync board / ADR 0011 async auth) and the principal resolver
  (ADR 0013/0014/0015) without changing any of them.

## Context

The app is live on Fly + Neon (ADR 0004) but had three operational blind spots:

1. **Health didn't reflect dependency health.** `GET /api/health` returned a static
   `{"status": "ok"}` — it stayed green even if Postgres was unreachable, so the keepalive ping and
   any external monitor couldn't distinguish "process up" from "actually serving". Neon scales to
   zero on the free tier, so a real readiness signal matters.
2. **No structured request logs.** There was no consistent, machine-parseable per-request record
   (method, path, status, latency, who) to reason about behaviour or debug an incident after the
   fact.
3. **No error sink.** An unhandled 500 in prod left only whatever landed in the container's stdout;
   nothing aggregated or alerted.

The constraints: keep the health happy path cheap (Fly + the keepalive workflow hit it frequently),
add nothing that runs — or phones home — in dev and tests by default, and never log or transmit
secrets (session cookies, PATs).

## Decision

Add a self-contained observability layer in [`app/observability.py`](../../backend/app/observability.py)
plus the readiness probe in [`app/main.py`](../../backend/app/main.py). No schema change, no new auth
path.

- **Readiness vs. liveness health.** `GET /api/health` becomes a **readiness** probe: it runs a cheap
  `SELECT 1` on the **sync board engine** (ADR 0008, via the request-scoped `get_db`) — DB reachable
  → `200 {"status": "ok"}` (the fast path, sub-ms warm); DB unreachable → `503 {"status":
  "unavailable"}`. A new `GET /api/health/live` is a static **liveness** probe (always `200` while
  the process serves), so an orchestrator can tell "process alive" apart from "DB ready". Making the
  existing endpoint DB-aware also means the keepalive ping now genuinely keeps **Neon** warm, not
  just Fly. Fly has no machine-level HTTP health check configured against it, so a `503` won't cause
  machine reaping; the keepalive poller already soft-fails and tolerates the cold-start latency.
- **Structured JSON request logging.** An HTTP middleware emits one JSON line per request on the
  `kanban.access` logger: `method`, `path`, `status_code`, `latency_ms`, and `principal_id` **where
  available**. Level is set by the **`LOG_LEVEL`** env var (default `INFO`). The principal id is
  populated by `app.authz.get_principal`, which now stashes `request.state.principal_id` when it
  resolves a cookie session or PAT to a user — the middleware reads it after the route runs. The
  formatter **allow-lists** the fields it serialises (never dumps `record.__dict__`) and logs only
  the URL **path** (no query string), so headers, cookies, and bearer tokens can never reach a log
  line.
- **Error tracking behind a DSN (Sentry), opt-in.** `init_error_tracking()` initialises Sentry
  **only** when **`SENTRY_DSN`** is set; unset → a pure no-op that doesn't even import the SDK. This
  mirrors the "GitHub OAuth routes only mount when creds are set" pattern (ADR 0011), so dev and the
  test suite (which set no DSN) report nowhere. `send_default_pii=False` keeps request headers,
  cookies, and PATs out of every event; tracing is off by default (`SENTRY_TRACES_SAMPLE_RATE=0`),
  opt-in via env. `sentry-sdk[fastapi]` is a runtime dependency so prod can enable it with a Fly
  secret and no code change; its FastAPI/Starlette integration auto-enables on `init()`.

## Consequences

- **Positive:** health now reflects real dependency reachability (proven by an integration test that
  points `get_db` at a dead address and asserts `503`); every request leaves a structured,
  greppable line attributable to a user; prod can turn on error aggregation with one secret.
  Everything is safe-by-default and off in dev/tests.
- **Neutral:** the access middleware wraps every request (including the frequent health ping) — cheap,
  but it does log those lines at `INFO`; raise `LOG_LEVEL` to quiet them. `principal_id` is only
  present for routes that go through `get_principal` (board-scoped `/api/v1`); infra/auth/webhook
  routes log it as absent.
- **Negative / deferred:** logs go to stdout only (Fly captures them) — no shipping to a log
  aggregator yet. Sentry is the chosen sink; swapping it would touch `init_error_tracking()` only.
  No metrics/tracing beyond Sentry's optional tracing. These are acceptable for the single-tenant
  deployment and can be revisited later.
