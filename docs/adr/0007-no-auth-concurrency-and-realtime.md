# ADR 0007 — No auth, last-write-wins concurrency, no real-time (MVP)

- **Status:** Accepted
- **Date:** 2026-07-07

## Context

REQS.md explicitly excludes authentication and billing ("just a simple app with no auth for now").
Multiple people may nonetheless view and edit the same board, and we must decide how much
concurrency/real-time machinery the MVP needs.

## Decision

- **No authentication or authorization.** All endpoints are open; there are no user accounts.
  `assignee` is therefore just free text (see ADR 0006).
- **Concurrency: last-write-wins.** No optimistic locking, versioning, or etags in the MVP.
- **No real-time sync.** The UI refetches after its own mutations and may refetch on window focus;
  there is no WebSocket/SSE server push. Other users see changes on their next refetch.

## Consequences

- **Positive:** Dramatically simpler backend and frontend — no auth flows, no session handling, no
  socket lifecycle, no conflict-resolution UI.
- **Negative:** Concurrent edits to the same card can silently overwrite each other; collaborators
  don't see live updates. Acceptable for a small-team MVP demo.
- **Future:** Auth, per-user identity for `assignee`, optimistic locking, and real-time updates are
  all deferred. The API-first design (ADR 0005) means auth can later be added as middleware without
  reshaping endpoints.
