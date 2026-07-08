---
shaping: true
---

# Milestone 3 — Frame (Accounts, Boards & Agent Access)

## Source

> I want to come up with new features for the next milestone. For example, I want users to be
> able to log in to the app via GitHub OAuth. make the implementation modular and flexible so that
> I can expand to Google OAuth and FastAPI-users in the future too. Also, I want human users and
> agents to be able to create and manage boards. Users should also be able to manage the auth for
> agents (via tokens etc.) Please suggest any useful features that I have overlooked for the next
> milestone, and let's discuss and iterate over plans for the next milestone together.

---

## Problem

Milestone 2 made the board **agent-writable** but left it a single, shared, ownerless space:
- **No identity for humans.** Anyone with the URL sees and (locally) edits the one board — ADR 0007's
  MVP "no auth" stance. There's no way to know *who* a human is.
- **One global board.** ADR 0006's single-table, single-board model. No way to separate work by
  project, team, or context.
- **Agent access is all-or-nothing.** V4's `API_TOKENS` is a flat, env-managed list of
  interchangeable secrets — no per-agent identity, no scoping, no self-serve management, no
  revocation beyond editing an env var, no record of which agent did what.

As soon as real people log in and agents write on their behalf, these gaps compound: you can't
share a board with a teammate, can't stop an agent from touching the wrong board, and can't tell
who (which human or which agent) made a change.

## Outcome

Humans sign in (starting with GitHub), own and share **boards**, and grant **agents** scoped,
revocable access they manage themselves — with a trustworthy record of who changed what. The auth
layer is **modular**: GitHub today, Google / a full user-management library (e.g. fastapi-users)
later, without reworking the app around it.

This evolves two accepted ADRs — 0007 (no-auth) and 0006 (single board) — so both will need new
ADRs recording the shift, in the same way ADR 0009/0010 evolved earlier decisions.
