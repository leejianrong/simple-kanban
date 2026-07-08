---
shaping: true
---

# Milestone 2 — Agent-Driven Task Tracking (Frame)

The "why" for the next milestone, above any solution. See `SHAPING.md` (this folder)
for requirements and shapes. MVP context lives in `../` (REQS/CONTEXT/PRD/SHAPING/
BREADBOARD + adr/0001–0008), now shipped as **v0.1.0**.

## Source (verbatim)

> Ok, looks like we've reached a milestone where we have a working MVP. Good job!
> Can you suggest some next steps? I am thinking now is a good time to do git tag so
> that a snapshot of the MVP is taken. After that, I want to look at features like
> ability to create multiple boards (so that I can see the seeded cards). I also want
> to move towards adding Github auth, and ultimately exposing an MCP or CLI that agents
> can use to interact with the kanban app. The next milestone should be to allow agents
> like claude code to use this kanban app to track the outstanding tasks (stories,
> epics) for this project itself.

> Can you suggest other important useful features I might have overlooked? I want to
> consider options and have a fuller picture before making a decision.

---

## Problem

The MVP is a single global board driven by one human clicking a UI, with **no auth**
(ADR 0007) and a **flat, single-board** data model (ADR 0006). But the intended future
— and the point of the API-first design (ADR 0005) — is that **autonomous agents (e.g.
Claude Code) drive the board programmatically**. Nothing today enables that safely:

- There is **no agent entry point** (no MCP server / CLI).
- The public deployment is **world-writable** — unsafe to point an agent at.
- The model **can't express real project work** — no epics/stories, labels, or priority.
- There is **no dedicated place** for this project's own tasks (only the demo board).
- The API lacks the **ergonomics programmatic clients need** (versioning, filtered/
  incremental queries, idempotent/bulk writes) and **no record of who changed what**.

## Outcome

**Claude Code can use the kanban app, through an agent interface, to track this
project's own outstanding work (epics and stories) — safely, and with a trustworthy
record of what it changed.** Success is dogfooding: this repo's backlog lives in the
app and an agent keeps it current.

Non-goals for this milestone are captured as lower-priority / out requirements in
`SHAPING.md` rather than here — framing stays at the "why" level.
