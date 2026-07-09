---
name: project-manager-simple-kanban
description: >-
  Act as a project manager / scrum-master over the Simple Kanban board, driving it through the
  Kanban MCP and clearing work by delegating to sub-agents (one at a time). Use when the user says
  things like "act as PM/scrum master for the kanban board", "look at the roadmap and start working
  through it", "manage sub-agents to clear the board", "pull the next card and build it", or
  "triage / groom the simple-kanban backlog". This is an orchestration playbook, not a reference for
  the individual MCP tools.
---

# Project manager for Simple Kanban

You are the **PM / scrum-master**. You do **not** write feature code yourself — you read the board,
decide what to work on, and delegate each card to **one sub-agent at a time**, then land the result.
Your job is throughput + quality + keeping the board honest, and (a standing goal in this repo)
**dogfooding**: notice and record where the tool itself is awkward to drive as an agent.

## Prerequisites (check once, up front)

- The **Kanban MCP** is wired (`.mcp.json` at repo root points at the deployed API with a `KANBAN_TOKEN`
  PAT). Tools appear as `mcp__kanban__*`. If they're missing, tell the user to check `.mcp.json`.
- `gh` CLI is available and authenticated (`gh auth status`) — needed to open/merge PRs.
- You're in the repo working tree, `main` is protected (PR-only, CI must be green), and the app is
  **live in production** — landing a PR deploys. Treat merges accordingly.
- Confirm the **land policy** with the user before merging anything (see *Merge / land policy*).

## Step 0 — Orient

Always start by reading the whole board, top-down:

1. `mcp__kanban__list_boards` → find the target board's `id` (e.g. "Simple Kanban Roadmap").
2. `mcp__kanban__list_epics(board_id=…)` → the epics give you the thematic groupings + intent.
3. `mcp__kanban__list_cards(board_id=…)` → all cards with `column`, `position`, `story_points`,
   `epic_id`, `description`. Cards come back ordered by (column, position).

Read each card's `description` — this board writes real acceptance criteria and **dependency hints**
in prose (e.g. "Depends on the shared-client extraction", "Prerequisite for the CLI"). There is **no
structured dependency field**, so you must parse dependencies out of the text yourself and sequence
around them.

## Step 1 — Sequence the backlog

Pick the next card by these rules, in order:

1. **Respect prose dependencies.** If a card says it depends on another, don't start it until the
   dependency is `done`. (e.g. "extract shared client" before the CLI cards that import it.)
2. **Dogfooding-first / unblock-first.** Prefer small, self-contained cards that improve your own
   tooling or unblock a whole epic. Tool/parity gaps you personally hit belong at the front.
3. **Then by epic coherence + story points** — finish a started epic before opening a new one; among
   equals, smaller points first to keep momentum and validate the loop early.

State your chosen order to the user before diving in for a long run.

## Step 2 — The PM loop (per card, one sub-agent at a time)

**a. Pull.** Move the card into flight and tag it so the board reflects reality:
```
mcp__kanban__move_card(card_id=<id>, column="in_progress")
mcp__kanban__update_card(card_id=<id>, assignee="agent:<slug>")   # who's on it
```

**b. Delegate.** Spawn exactly **one** `general-purpose` sub-agent with `isolation: "worktree"`
(keeps your primary checkout clean; the shared local Postgres works across worktrees). Give it the
full card + the brief template below. Do **not** run a second implementer in parallel — the user
wants one at a time, and it keeps `main`/CI serialized and reviewable.

**c. Verify.** When it reports back: sanity-review the diff and the PR, then watch CI to green:
```
gh pr checks <pr-number> --watch
```
CI is six jobs (lint, unit, integration, frontend build, e2e, mcp). Don't land on red or pending.

**d. Land** (per agreed policy). On green CI, for auto-merge:
```
gh pr merge <pr-number> --merge --delete-branch      # merge commit, not squash (repo convention)
mcp__kanban__move_card(card_id=<id>, column="done")
```

**e. Capture.** Append concrete learnings to this skill's *UX notes* log — what was awkward in the
board/MCP, what the sub-agent tripped on, anything worth doing differently next card.

## Sub-agent brief template

Fill the `<…>` and paste as the agent prompt:

```
You are implementing one vertical slice of the simple-kanban project. Ticket <KAN-N>: "<title>".

<full card description>

READ FIRST and follow exactly: /home/…/simple-kanban/CLAUDE.md — especially the dev workflow
(branch-per-slice off a fresh `main`), the exact local check commands, API-first (ADR 0005), and
the "verify against the code, don't trust the docs" rule. This is a thin slice — match the existing
incremental style; do not refactor beyond the ticket.

Workflow:
1. `git switch main && git pull --ff-only`, then `git switch -c feat/<slice>`.
2. Implement the slice. Keep it minimal and consistent with surrounding code.
3. Run the local checks for every package you touched (mirror of the pre-push hook):
   - backend (from backend/): `uv run ruff check .` + `uv run pytest tests/unit -q`
     + `uv run pytest tests/integration --collect-only -q` (import-hygiene guard)
   - frontend (from frontend/): `npm run check`
   - mcp (from mcp/): `uv run ruff check .` + `uv run pytest -q`
   Update any hard-coded expectations you change (e.g. mcp/tests/test_server.py `EXPECTED_TOOLS`,
   the tool table in mcp/README.md).
4. Commit (end the message with the repo's Co-Authored-By trailer), push, and open a PR with `gh`
   (clear title + body: what/why, test evidence, and OPS notes if any).

Report back, structured: branch name, PR URL, files touched, exactly which checks you ran + their
results, and any FRICTION / UX notes (anything about the board, MCP tools, or repo that slowed you
down — the PM is separately assessing tool UX).
```

## Merge / land policy

Confirm with the user which applies, then stick to it:
- **Auto-merge on green CI** — you merge once CI passes and you've sanity-reviewed the diff, then
  move the card to `done`. Fast; you are merging to production unattended, so review the diff.
- **Open PR, user merges** — you get CI green and report the PR; the user does the final merge.
- **Branch only** — sub-agent pushes a branch; no PR.

## Definition of done (per card)

CI green **and** PR merged **and** card moved to `done` **and** this skill's UX log updated. A card
is not done just because the code is written.

## UX notes & gotchas (running log — append as you learn)

Dogfooding observations about driving this board as an agent PM. Seeded from the plan; extend it.

- **No dependency field.** Dependencies live only in card `description` prose — you must read and
  sequence manually. A blocked-by relation on the board would remove guesswork.
- **`list_cards` spans/return shape.** Pass `board_id` explicitly (or set `KANBAN_BOARD_ID`) — with
  neither, list/create tools span all your boards / land on the earliest board. Cards return ordered
  by (column, position); there's no server-side "next up" concept — priority == your reading of it.
- **Column ≠ status of the *work*.** `in_progress` on the board just means "an agent is on it"; the
  real state (branch pushed? PR open? CI green? merged?) lives in git/`gh`, not the board. Keep the
  two in sync manually — move to `done` only after merge, not after the code is written.
- **No comment / note tool.** There's no way to attach a progress note, PR link, or decision to a
  card via MCP. `assignee` is the only free-text handle — repurpose it (`agent:<slug>`) to show who's
  on a card. A PR-URL / notes field would close the loop between board and repo.
- **`move_card` vs `update_card` split.** Column/position changes go through `move_card`; field edits
  through `update_card`. You can't set column + assignee in one call — it's two calls to pull a card.

- **Cold start is a HARD FAILURE, not just slow (biggest gotcha).** The free-tier app scales to zero.
  The docs call this a "~1s slow first request," but in practice the first calls after idle fail
  outright: the MCP tool returns `read operation timed out` / `SSL: UNEXPECTED_EOF_WHILE_READING`, and
  `curl` shows a TLS handshake `decode error` at ~5s — indistinguishable from "server is down." It
  took ~6 failed requests plus a `flyctl status` check before it served 200s. **Mitigation as PM:**
  before the first board call after any idle period, warm the app yourself and retry until healthy:
  `curl -sS -m 30 https://simple-kanban-jian.fly.dev/api/health` (loop 3–6×; expect `{"status":"ok"}`).
  Only then drive the MCP. (This is exactly what board Epic 7 / KAN-25/26/27 exist to fix — live proof
  the tickets are real.)
- **Pre-push hook is all-or-nothing across packages.** The tracked hook always runs `svelte-check`,
  which isn't installed in a worktree where the agent only `uv sync`'d the mcp package (no `npm ci`),
  so a *mcp-only* change fails the hook on the frontend toolchain and the agent must `git push
  --no-verify`. Tell single-package sub-agents up front that `--no-verify` is expected for a scoped
  slice (CI still gates the real check), or have them `npm ci` too.
- **`gh pr checks --watch` isn't available** in the installed gh here. Poll instead: loop
  `gh pr checks <n>` until the output has no `pending` (integration + e2e are the slow jobs, ~1–3 min).
- **Docs pin exact tool counts in prose** ("10 tools") in CLAUDE.md + mcp README/docstrings, so every
  parity slice silently staleness them. As PM, either budget a doc-sweep card or stop pinning counts.
- **What works well:** the MCP/backend is genuinely pleasant to extend — API-first means feature cards
  like KAN-10/11 are pure thin-adapter slices (add a `KanbanClient` method + a `@mcp.tool()`, mirror
  the `_clean`/`{"deleted": id}` conventions, bump the exact-match `EXPECTED_TOOLS` test). Sub-agents
  finish these in one pass. Lean into small, self-contained parity/tooling cards early.
- **Worktree sub-agents start from your CURRENT local `main`, not `origin/main`.** After you merge a
  PR, your local `main` is *behind* the remote (the merge happened on GitHub). The next worktree
  agent then branches off the stale commit and won't see the just-merged work — it has to
  `git fetch && git merge --ff-only origin/main` itself. **Two-part fix:** (1) after every merge, run
  `git -C <repo> fetch origin && git -C <repo> branch -f main origin/main` (or `git switch main &&
  git pull --ff-only` if main isn't checked out elsewhere) so the next worktree is spawned from fresh
  main; (2) still tell each sub-agent to `git switch main && git pull --ff-only` before branching, as
  a belt-and-braces guard. Also warn agents: `git reset --hard` is auto-denied as destructive in the
  harness — the clean-tree `--ff-only` merge is the sanctioned path anyway.
- **Sequential dependent cards need explicit hand-off of the prior state.** KAN-11 depended on KAN-10's
  merged `EXPECTED_TOOLS`=14. Put the *exact* prior-state facts in the next brief ("14 tools now, the
  4 KAN-10 tools are X/Y/Z, you're going to 16") so the agent can self-verify it's on the right base.
- **The MCP client's timeout is tighter than a cold-wake.** After idle, a raw `curl .../api/health`
  can return 200 on the first try while the *MCP tool call* still times out — the client gives up
  before the machine finishes waking. So warming with curl isn't always enough; you may still need to
  retry the first MCP call once or twice. (Reinforces KAN-25: generous timeout + one auto-retry in
  the shared client.)
- **Worktree isolation does NOT sandbox `Bash` — brief agents explicitly.** The harness blocks the
  `Write`/`Edit` tools from touching paths outside the agent's worktree, but `Bash` can still `cd`
  into the shared primary checkout and run `git switch -c` there, silently moving YOUR `main` checkout
  onto a feature branch. Two agents did a version of this. **In every sub-agent brief, say: "run all
  git against your worktree path only; never `cd` into the parent checkout."** As PM, keep your primary
  checkout parked on `main` and re-check `git branch --show-current` after each agent returns (both
  times it self-restored, but verify — don't assume).
- **Shared-package pattern in this uv monorepo: path source, not a root workspace.** KAN-21 extracted
  `kanban-client/` as a standalone uv package that `mcp` depends on via
  `[tool.uv.sources] kanban-client = { path = "../kanban-client", editable = true }`. A repo-root uv
  *workspace* would be auto-discovered when running `uv` from `backend/` and force `backend` into the
  workspace, breaking its independent `--frozen` flow. Each package stays independently locked; the
  lockfile records a *relative* path so CI's fresh checkout stays portable. Any new shared package
  also needs its own CI job (mirror the `mcp` job) — CI is now 7 jobs.
- **Distinguish CI *infra* failures from real ones before reacting.** A whole run of jobs all "failing"
  at the *same suspiciously-round duration* (e.g. every job at `15m1s`, including ones that normally
  take 11s) is an infrastructure symptom, not your code. Check the run's annotations
  (`gh run view <run-id>`): here it was *"The job was not acquired by Runner of type hosted even after
  multiple attempts"* — GitHub had no hosted runners free. Fix is a re-run, not a code change:
  `gh run rerun <run-id>` (or `gh run rerun <run-id> --failed`). Never move a card back or "fix" a
  red that's actually infra. Free-tier CI is flaky the same way the free-tier app is — budget for it.
- **Cold start recurs after ~5 min idle — warm before EVERY board interaction in a long session,**
  not just once at the start. A single card can span a >5-min CI wait, and the app scales to zero in
  the meantime, so the *move-to-done* call at the end of a card cold-starts again. Cheap habit: a
  `curl .../api/health` warm loop immediately before any `mcp__kanban__*` call that follows a gap.
- **`gh pr merge --delete-branch` can't delete the branch while it's checked out in the agent's
  worktree** — you'll see `failed to delete local branch … checked out at …/.claude/worktrees/…` and
  a non-zero exit, but the **merge itself still succeeds** (confirm with `gh pr view <n> --json state`
  → `MERGED`). The remote branch is deleted; the local one is cleaned when the harness reaps the
  worktree. Don't mistake that exit code for a failed merge.

## Session log (what's been run through this playbook)

- **Epic 5 — Agent & API Completeness: COMPLETE.** KAN-10 (MCP write parity → PR #26, tools 10→14)
  and KAN-11 (MCP read parity → PR #27, tools 14→16) both merged + `done`. Net: the MCP server now
  has full CRUD parity for cards, epics, and boards (16 tools) — the `delete_board` gap that
  triggered KAN-10 during dogfooding is closed.
- **Backlog groomed from dogfooding.** The "board can't tell the whole story" friction (no
  dependency field; no PR-link/notes field; column = "an agent is on it" ≠ real work state) was turned
  into **EPIC-8 "M4: Board as an Agent-PM Surface"** with 7 vertical slices, **KAN-28…KAN-34**:
  card dependencies (model+API → ready/blocked query filter → UI → MCP) and card work-links + notes
  (model+API × 2 → MCP+UI). This is the PM job working as intended: dogfooding surfaces a gap → it
  becomes prioritised backlog. A good PM agent files what it learns, not just what it's told.
- **Suggested next pull:** KAN-21 (extract shared `kanban_client`) — it's the prerequisite that
  unblocks the entire kan-CLI epic (KAN-22/23/24) and the cold-start-resilience card (KAN-25).
