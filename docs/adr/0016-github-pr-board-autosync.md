# ADR 0016 — GitHub PR-board auto-sync (close the loop)

- **Status:** Accepted
- **Date:** 2026-07-13
- **Context source:** Epic **EPIC-10** (GitHub PR-board auto-sync). Realises the API-first,
  agent-friendly intent of ADR 0005 for the "agent as PM" workflow. Builds on ADR 0012 (multi-board
  with ownership), ADR 0013 (board authorization), and ADR 0014 / 0015 (agent PATs) — reusing their
  ownership model rather than adding a new one. Delivered as cards KAN-42 (webhook receiver),
  KAN-43 (event mapping), and KAN-44 (this ADR + the [setup guide](../guides/autosync-github-setup.md)).

## Context

The board and the git workflow were two disconnected systems. A human or agent picked up a card,
opened a PR, waited on CI, merged, and then had to come back and hand-update the card — attach the
PR link, note the CI result, drag it to Done. For the agent-as-PM workflow this project is built
around (ADR 0005), that manual reconciliation is exactly the toil we want the tooling to remove: the
information already exists in GitHub, and the board should reflect it.

The natural mechanism is an **inbound webhook** — GitHub already emits `pull_request`, `check_suite`,
and `status` events, and posting them to the board lets the board react in real time with no polling.
Three questions had to be resolved:

1. **How does an inbound webhook authenticate?** It isn't a logged-in user, so it can't carry a
   cookie session or a PAT and can't go through the `get_principal` / `authorize_board` path that
   guards the rest of `/api/v1` (ADR 0013).
2. **How does an event find its card?** Nothing in a raw GitHub payload references a board or a card
   id.
3. **How much should it be allowed to do without a human?** Attaching a link is cheap and reversible;
   silently moving a card to Done on every merge is a stronger claim that some owners will want and
   others won't.

## Decision

**Close the loop with a single inbound GitHub webhook, `POST /api/v1/webhooks/github`** (KAN-42,
[`app/routers/webhooks.py`](../../backend/app/routers/webhooks.py)). It verifies, parses, dispatches
per event type, and acks `200`. The mapping onto board side effects lives in
[`app/autosync.py`](../../backend/app/autosync.py) (KAN-43).

- **HMAC-signature auth, not principal-gated.** The endpoint authenticates each delivery by
  recomputing HMAC-SHA256 over the **raw** request body keyed on a shared `WEBHOOK_SECRET` and
  constant-time-comparing it against the `X-Hub-Signature-256` header. `WEBHOOK_SECRET` unset →
  **503** (never skip verification silently — the feature is simply off until configured); missing /
  malformed / mismatched signature → **401**; unknown event type → **200** ignored. This route
  deliberately does **not** depend on `get_principal` / `authorize_board` (ADR 0013): the caller is
  GitHub, not a user, so the signature is the whole authentication and the writes act as **the
  system** (comments carry a NULL `author_id`).
- **Map events to cards by ticket.** Auto-sync parses a `KAN-<n>` (case-insensitive) out of the PR
  branch name or title (head branch for CI events), resolves the card and its board, and no-ops when
  no ticket is present — so a payload without a ticket never even opens a DB session. `pull_request`
  `opened`/`reopened` attaches the PR URL as an idempotent `PR` work-link; `check_suite`/`status`
  post a CI-result comment; a merged PR advances the card to Done.
- **Per-board opt-in, default OFF (the human-in-the-loop safeguard).** Two boolean flags on the
  `board` table (migration `0011`), both `NOT NULL DEFAULT false`, settable via
  `PATCH /api/v1/boards/{id}` (on `BoardUpdate`/`BoardRead`):
  - **`autosync_enabled`** — master switch. Every auto-sync action first resolves the card's board
    and does nothing unless this is true. Boards are opted **out** by default, so the pre-existing
    behaviour — a human moves cards by hand — is unchanged for every board until its owner turns
    auto-sync on. (Decided with the maintainer, 2026-07-13.)
  - **`autosync_advance_to_done`** — a **separate** switch gating *only* the merge→Done move. Even
    with auto-sync on, a merged PR does **not** move the card unless this second flag is also true, so
    "Done" stays a deliberate human decision by default. (Decided with the maintainer, 2026-07-13.)
- **Reuse the existing ownership model for the toggles.** Turning the flags on/off is a normal
  owner-gated `PATCH /boards/{id}` (ADR 0013) authenticated by the owner's session or PAT (ADR
  0014/0015) — no new authorization surface. The webhook's own writes are bounded by whatever the
  owner opted that board into, so the opt-in flag *is* the authorization for the system-level writes.

## Consequences

- **Positive:** the board reflects real PR/CI state automatically for boards that want it, removing
  the manual reconciliation step in the agent-as-PM loop (ADR 0005). The design adds no new principal
  type or auth path — the webhook is a self-contained HMAC-verified endpoint, and the per-board
  toggles ride on the existing owner-gated board PATCH. Everything is safe-by-default: an unset
  secret, or a board left at its defaults, does nothing.
- **Neutral:** auto-sync writes are un-attributed (system comments, NULL author) — consistent with
  the fact that GitHub, not a user, triggered them. The receiver stays a thin, standalone router; the
  mapping opens its own sync session (`SessionLocal`) rather than the request-scoped `get_db`, since
  it isn't serving a user request.
- **Negative / deferred:** a single shared `WEBHOOK_SECRET` covers all repositories/boards (no
  per-board webhook secret); ticket matching is a simple `KAN-<n>` scan of branch/title (a PR that
  never names its ticket is invisible to auto-sync); there's no retro-fill of events that arrive
  before a board opts in, and no delivery retry/queue beyond GitHub's own redelivery. These are
  acceptable for the single-tenant/dogfooding deployment and can be revisited if multi-repo or
  multi-tenant needs arise.
