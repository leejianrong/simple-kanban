# ADR 0010 — Optional bearer-token auth on writes

- **Status:** Accepted
- **Date:** 2026-07-08
- **Context source:** Milestone 2 (Agent-Driven Task Tracking), requirement R3.1; evolves the
  "no auth" stance of ADR 0007 (see `docs/milestone-2/`, part P2).

## Context

ADR 0007 deliberately shipped the MVP with **no authentication** — a single shared board, last-write-
wins, no accounts — because the only client was a trusted same-origin SPA. Milestone 2 adds a second
class of client: non-interactive **agents** (the coming MCP server, ADR 0005) that mutate the board
over the API. R3.1 requires those agents to authenticate with an API token.

The constraint is that introducing auth must not disrupt what already works: the SPA sends no
credentials, local dev is tokenless, and ~40 existing write tests issue unauthenticated writes.
Scoped read/write tokens and revocation are wanted eventually (R3.4) but are explicitly **Later**.

## Decision

- **Bearer token on mutating routes only.** All `POST`/`PATCH`/`DELETE`/`move` routes (cards **and**
  epics) depend on a `require_token` FastAPI dependency ([backend/app/auth.py](../../backend/app/auth.py));
  it checks `Authorization: Bearer <token>`. **Reads stay open** — the SPA never sends a token.
- **Tokens come from `API_TOKENS`** — a comma-separated env var, parsed per request (so a deployment
  can rotate it and tests can toggle it without a rebuild).
- **Unset ⇒ auth disabled ⇒ writes open.** This is the default and preserves ADR 0007's behaviour for
  the SPA, local dev, and the existing test suite. **Set ⇒ enforced:** a missing or unlisted token on
  a write returns **`401`** with `WWW-Authenticate: Bearer`.
- **Flat token list, no scopes.** Any listed token authorizes any write. Per-token read/write scoping
  and revocation (R3.4) are deferred.
- **Production opts in** by setting `API_TOKENS` as a Fly secret. Until it is set, prod writes remain
  open (unchanged) — setting the secret is the switch that turns enforcement on.

## Consequences

- **Positive:** agents can authenticate non-interactively; the SPA and dev loop are untouched; the
  feature is a single dependency + env var with no schema change and no migration. Reads staying open
  keeps the board publicly viewable, matching the MVP.
- **Evolves ADR 0007.** That ADR's "no auth" was an explicit MVP simplification for a single trusted
  client; a second, untrusted client class is exactly the trigger it anticipated. Last-write-wins and
  no-real-time are unchanged.
- **Negative / deferred:** a flat token list means no per-agent identity, audit, or revocation beyond
  editing `API_TOKENS`; no rate limiting. Because auth is off when unset, a misconfigured production
  (secret never set) silently leaves writes open — acceptance for the milestone is that prod sets the
  secret. Request-body validation (`422`) may surface before the token check (`401`) on a malformed
  unauthenticated write; the schema is already public via `/docs`, so this leaks nothing sensitive.
