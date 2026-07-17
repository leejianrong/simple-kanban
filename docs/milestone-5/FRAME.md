---
shaping: true
---

# Milestone 5 — Frame (The board as a human↔agent coordination surface)

## Source

> Leave it in the backlog for now. I want to move on to planning Milestone 5. Discuss it with me and
> let's chart out the epics and directions for this app. I am interested in exploring what's the delta
> between simple-kanban (ours) and other tools like Jira, Trello, etc. Are there any good points from
> those apps that we can adopt?

> I want to support solo developers and teams that work with multiple LLM agents to do work. Not sure
> exactly how the humans interact with the agents yet, but keep this in mind when designing the
> product.

> When i said that, i meant it more in terms of user experience and ergonomics. The tool should be
> easy and intuitive for both humans and agents to use. However, looking at my personal usage so far,
> I prefer for agents to manage the board completely, and for me to instruct either from a CLI or (in
> the future) from a messaging app like telegram or slack. Maybe for now, to keep it simple, we can
> assume that users will bring their own agent, and our responsibility is to make sure the tool is
> easy for agents to use. However, the UI is still important for humans as i find myself going to look
> at the visual board to help me keep track of progress or stay up to date with what my agents are
> working on and have completed in the past.

> For the "needs-human" mechanism, let's go with what you recommend (a lightweight flag/state on a
> card is fine).

---

## Problem

Milestones 2–4 made the board agent-*writable* and collaborative, but it is still shaped like a
human-operated Kanban tool that agents happen to be able to call. For the target user — a **solo
developer or small team directing a fleet of LLM agents** — that shape leaves ergonomic gaps on both
sides:

- **Agents can't be dispatched.** There's no priority, no "give me the next actionable card," and no
  fleet-safe claim. To run the board an agent (or a PM agent) must read every column and sequence by
  hand — exactly what happened while dogfooding EPIC-4: the PM agent hand-sequenced the backlog and
  tracked fleet state in its head because the board offered no dispatch primitive.
- **Humans can't observe at a glance.** The UI is CRUD-shaped (create/edit forms, drag-and-drop) —
  built for a human doing data entry. But the human here doesn't operate the board; they want to
  *watch* it: what are my agents doing now, what did they finish, what's blocked or waiting on me.
- **There's no structured human↔agent handoff.** When an agent hits a decision it can't make, there's
  no in-product signal — it happens out of band (in EPIC-4, approvals happened in chat). The human has
  no single "what needs me" surface.
- **The everyday triage vocabulary is missing.** Labels, priority, due dates, saved views, and search
  — table stakes in Trello/Linear/Jira — don't exist, so a board is hard to navigate as it grows.

## Outcome

simple-kanban becomes the **coordination substrate for human-directed agent fleets**. Two audiences,
two surfaces, one board:

- **Agents *operate* the board** through a frictionless, safe write surface — deterministic dispatch,
  atomic fleet-safe claim, priority/labels/due dates, scoped tokens — reachable identically from the
  API, the MCP server, and the `kan` CLI (API-first, ADR 0005).
- **Humans *observe and steer*** through a glanceable awareness UI (fleet status, a "needs your
  attention" surface, activity/history, table + saved views, reporting) and **instruct via the CLI**
  today (a messaging bridge such as Telegram/Slack is a later milestone).

**Bring your own agent.** M5 builds the *substrate*, not the agent or an orchestrator — our
responsibility is making the board effortless for someone else's agent(s) to run, and effortless for a
human to keep track of.

This preserves the deliberate **no-real-time / last-write-wins** stance (ADR 0007): awareness is
poll/refresh, not websockets; fleet-safe dispatch uses a DB-level primitive (`SELECT … FOR UPDATE SKIP
LOCKED`), not application locking. It also holds the **"stay simple"** line — no Jira-style workflow
engine, custom-field explosion, or time tracking.

Expected new ADRs: **agent operating ergonomics** (dispatch + fleet-safe claim semantics; scoped
tokens) and **human-observe UI direction** (awareness-first UI; the `needs_human` handoff flag). ADR
0007 (no-real-time/LWW) is reaffirmed, not evolved.
