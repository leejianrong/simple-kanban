# ADR 0014 — Self-serve agent personal access tokens

- **Status:** Accepted
- **Date:** 2026-07-09
- **Context source:** Milestone 3 (Accounts, Boards & Agent Access), requirements R4.1/R4.3/R7.1,
  decisions D3/D5; Shape A part **A6**; BREADBOARD places **S4** (Tokens page) + **S5** (principal
  resolver). Builds on ADR 0011 (users) and ADR 0013 (board authorization / one authorization
  layer). **Supersedes ADR 0010's `API_TOKENS`** as the *agent authentication mechanism*. Delivered
  as slice **V9**.

## Context

V4 (ADR 0010) gave agents a single shared, env-managed bearer list (`API_TOKENS`): flat,
all-or-nothing, not tied to any user, rotated by editing an env var. V8 (ADR 0013) then made
`/api/v1` owner-gated and kept that bearer alive only as a **transitional, unscoped SERVICE bypass**.
Milestone 3's goal (R4.1/R4.3) is proper agent access: users create and revoke their **own** named
tokens in the UI, each token **acts as its owning user** (attributable, inheriting that user's board
access), and secrets are **hashed at rest** and shown once (R7.1). That's what lets an agent (the MCP
server) work on exactly the boards its owner can — no separate agent identity, no shared secret.

## Decision

- **`personal_access_token` table** (`user_id`→user `ON DELETE CASCADE`, `name`, `token_hash`,
  `token_prefix`, `created_at`, `last_used_at`, `expires_at`). Migration `0006`.
- **Hash at rest, never the secret (R7.1).** The raw token is `kanban_pat_<43 url-safe chars>` (a
  256-bit random secret), returned **once** on creation. We store only **HMAC-SHA256 keyed with
  `AUTH_SECRET`** (a pepper) plus a short non-secret `token_prefix` for the UI list.
- **Fast, indexable hash — deliberately *not* bcrypt/argon2.** Auth is a single
  `WHERE token_hash = :h` lookup. Password hashes salt per row (so you can't look a token up — you'd
  scan and slow-compare every row) and exist to slow brute force on *low-entropy passwords*; a
  256-bit random token needs neither. The pepper means a stolen DB alone can't verify guessed tokens.
- **A PAT is the third branch of the one principal resolver (ADR 0013).** `get_principal` resolves:
  cookie session → `User`; else a valid PAT bearer → its owning `User`; else an `API_TOKENS` bearer →
  SERVICE; else `401`. A PAT-resolved `User` flows into the **same** `authorize_board` check a human
  uses — so an agent is owner-gated *identically* to its owner (403 on others' boards). The PAT path
  is fully **sync** (our table, indexed lookup on the sync board engine, ADR 0008); only the human
  cookie path touches the async engine. Each successful auth stamps `last_used_at`.
- **`/api/v1/tokens` CRUD, per user.** `POST` (returns the secret once), `GET` (metadata only — never
  the secret), `DELETE` (revoke = hard-delete; a revoked token simply isn't found → `401`). All
  require a real `User` principal (`require_user`); the SERVICE bypass is **not** a user and gets
  `403` (token management is inherently per-user). Optional `expires_at` is enforced at auth time.
- **A token acts *as* its owning user, with no per-token scope (D5).** Which boards, and read-vs-write
  scoping, are **Later** (R4.2). Attribution (user + token) is preserved for a future audit trail
  (R5.1).
- **Tokens UI page (S4).** A top-bar **Tokens** view: create (name → reveal-once with copy), list
  (name, prefix, created / last-used / expires), revoke-with-confirm.
- **`API_TOKENS` SERVICE bypass is retained for one more slice.** ADR 0010 is superseded *as the
  agent mechanism* (agents should now use PATs), but the unscoped SERVICE bypass still exists until
  **V10**, which rewires the MCP server onto PATs and then removes it (drop the `SERVICE` branch in
  `app/authz.py` + the Fly `API_TOKENS` secret). This keeps the transitional MCP path and the e2e
  cleanup helpers working during V9→V10; ripping it out now would buy nothing this slice.

## Consequences

- **Positive:** agents get self-serve, revocable, **owner-scoped** access with a single line of
  reuse — they plug into the exact authorization layer humans use (ADR 0013). Secrets are hashed +
  peppered and shown once; `last_used_at` gives a usage signal and seeds a future audit trail;
  tokens are attributable to (user + name).
- **Neutral:** `last_used_at` is a small write on the (otherwise read) auth path — cheap and
  best-effort; could be throttled/async later if it ever matters.
- **Negative / deferred:** no per-token board or read/write **scope** (R4.2), no roles (R3.2) or
  sharing (R3.3), and only a minimal usage signal rather than a full **audit trail** (R5.1) — all
  Later. The transitional `API_TOKENS` SERVICE bypass still exists until V10 removes it.
