# Agent onboarding guide

This guide gets a coding agent — Claude Code, or anything that speaks MCP — driving a
Simple Kanban board end to end: minting a token, wiring the MCP server, verifying the
connection, and running real workflows. There's also a CLI path for CI and non-MCP agents.

If you just want the short version: log in to the [hosted board](https://simple-kanban-jian.fly.dev),
create a personal access token in the **Tokens** tab, drop it into `.mcp.json` alongside
the `uv` server entry from [`.mcp.json.example`](../../.mcp.json.example), and ask your
agent to "list my boards".

## Why this board is agent-friendly

Simple Kanban is API-first by design (ADR [0005](../adr/0005-api-first-mcp-ready.md)):
every action the web UI can take is a plain REST call under `/api/v1`, and the UI is just
the first client rather than the only way in. The MCP server and the `kan` CLI are both
thin adapters over that same surface — one tool (or subcommand) per endpoint — so an agent
gets full CRUD parity with a human, including epics, card dependencies, work-links, and
comments. There's no hidden capability locked behind the browser.

That parity is the whole point. You can hand a card to an agent, and it can read the card,
see what's blocking it, claim it, attach a PR link, comment, and move it to Done, all
through tool calls.

## 1. Get access

You have two options.

**Use the hosted instance.** The board is live at
[simple-kanban-jian.fly.dev](https://simple-kanban-jian.fly.dev). Log in with GitHub. Your
first login claims any unclaimed boards and gives you a session; from there you own your
boards and only you can see or change them. This is the fastest way to try things.

**Self-host your own.** If you want an instance your team controls — which today you need
for more than one person, see [Single-owner boards](#single-owner-boards-and-what-that-means-today)
below — run it yourself. See [Self-hosting](#self-hosting) at the end.

Either way, the rest of this guide is the same; only `KANBAN_API_URL` changes.

## 2. Mint a personal access token (PAT)

`/api/v1` is auth-required for every request (ADR [0013](../adr/0013-board-authorization.md)),
and agents authenticate with a per-user PAT (ADR [0014](../adr/0014-agent-personal-access-tokens.md)).
There is no shared service token — the old `API_TOKENS` mechanism was removed in
[V10](../adr/0015-mcp-board-scoping-and-retiring-api-tokens.md).

1. Log in to the board (hosted or your own).
2. Open the **Tokens** tab in the top bar.
3. Click **New token**, give it a name, and create it.
4. Copy the `kanban_pat_…` secret. It is shown **once** — the server only stores a hash, so
   if you lose it you revoke it and mint a new one.

A PAT authenticates **as you**. It is owner-gated exactly like your logged-in session: it
can only touch boards you own. A board id you don't own returns `403`; a bad or empty token
returns `401`. Revoke a token any time from the same Tokens tab.

## 3. Wire the MCP server into Claude Code

Claude Code discovers project-scoped MCP servers from a `.mcp.json` at the repo root. Copy
[`.mcp.json.example`](../../.mcp.json.example) to `.mcp.json` and keep the server entry you
want. Full details are in [`mcp/README.md`](../../mcp/README.md); the essentials follow.

### The way that works today: run from source with `uv`

This needs a checkout of the repo and [`uv`](https://docs.astral.sh/uv/) installed. It runs
the server straight from `mcp/`, so there's nothing to download or build:

```json
{
  "mcpServers": {
    "kanban": {
      "command": "uv",
      "args": ["run", "--directory", "./mcp", "python", "-m", "kanban_mcp"],
      "env": {
        "KANBAN_API_URL": "https://simple-kanban-jian.fly.dev",
        "KANBAN_TOKEN": "kanban_pat_…",
        "KANBAN_BOARD_ID": "1"
      }
    }
  }
}
```

Three env vars carry the config:

- `KANBAN_API_URL` — the API origin. Use `https://simple-kanban-jian.fly.dev` for the hosted
  board, or `http://localhost:8000` for a local backend. The `/api/v1` prefix is added for you.
- `KANBAN_TOKEN` — your `kanban_pat_…` from step 2. Required; empty or bad → `401`.
- `KANBAN_BOARD_ID` — the default board (an integer id) for calls that omit `board_id`. **Set
  this.** If you leave it empty, `list_*` tools span *all* your boards and `create_*` tools land
  on your *earliest* board, which is an easy way to write to the wrong place. The example presets
  it to `1` (the seeded default board) — run `list_boards` once and change it to your real id.

`--directory ./mcp` is relative to where Claude Code launches the server (the repo root); use
an absolute path if you run the client from elsewhere.

### The way that will work once a release is cut: the ghcr.io image

`.mcp.json.example` also ships a `kanban-docker` entry that runs a prebuilt image with no
Python, no `uv`, and no checkout:

```json
{
  "mcpServers": {
    "kanban": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "KANBAN_API_URL",
        "-e", "KANBAN_TOKEN",
        "-e", "KANBAN_BOARD_ID",
        "ghcr.io/leejianrong/simple-kanban-mcp:latest"
      ],
      "env": {
        "KANBAN_API_URL": "https://simple-kanban-jian.fly.dev",
        "KANBAN_TOKEN": "kanban_pat_…",
        "KANBAN_BOARD_ID": "1"
      }
    }
  }
}
```

**This is not available yet.** The image is published only by the tag-triggered
`publish-mcp-image.yml` workflow, and no versioned release has been cut that runs it — the
`ghcr.io/leejianrong/simple-kanban-mcp` package does not exist today. Use the `uv` entry above
until a `v*` tag ships the image. (The `-e NAME` flags with no `=value` forward values from the
`env` block into the container, keeping the token out of the argument list.)

## 4. Verify it works

Restart Claude Code so it picks up `.mcp.json`, approve the `kanban` server when prompted, then
ask the agent to run two tools:

1. **`warmup`** — pings the unauthenticated health endpoint and wakes a scaled-to-zero Fly + Neon
   deploy. The first request after idle is slow (a documented ~1s cold start), so this pays that
   cost up front. A healthy response reports the API is up.
2. **`list_boards`** — returns the boards you own, each with an `id` and `name`. Seeing your board
   here confirms the token resolved to your user and auth is working.

If `list_boards` comes back empty on the hosted instance, log in to the web UI once first so your
first login claims a board. If it returns `401`, the token is wrong or unset; `403` on a specific
board means that board isn't yours.

## 5. Example agent workflows

These use the real MCP tool names (see the full table in [`mcp/README.md`](../../mcp/README.md)).
Card columns are `todo`, `in_progress`, and `done`.

**Pick up a card and start work.**

```
list_cards(column="todo")          # find something to do
claim_card(card_id, assignee="claude")   # assigns it and moves it to in_progress
add_comment(card_id, body="Starting on this — will open a PR shortly.")
```

**Record a blocker, then a fix.**

```
add_dependency(card_id, blocker_id)   # this card is now blocked by another
list_dependencies(card_id)            # see blocked_by / blocks
add_link(card_id, label="PR #57", url="https://github.com/leejianrong/simple-kanban/pull/57")
add_comment(card_id, body="Fix is up in PR #57, waiting on review.")
```

**Finish and close out.**

```
remove_dependency(card_id, blocker_id)   # blocker cleared
move_card(card_id, column="done")
```

**Plan a chunk of work.** Create an epic and hang stories off it:

```
create_epic(name="Onboarding flow", description="New-user first-run experience")
create_card(title="Landing page", column="todo", epic_id=<epic id>)
create_card(title="GitHub login button", column="todo", epic_id=<epic id>)
```

## 6. CLI path (for CI and non-MCP agents)

If your automation isn't an MCP client — a CI job, a shell script, an agent that shells out —
use the `kan` CLI. It's the same thin adapter over `/api/v1`, exposed as subcommands. Full
reference: [`kanban-cli/README.md`](../../kanban-cli/README.md).

**Install from git (works today):**

```bash
uv tool install "git+https://github.com/leejianrong/simple-kanban.git#subdirectory=kanban-cli"
```

`uv` clones the repo and resolves the sibling `kanban-client` path dependency from the same
checkout, so `kan` lands on your `PATH` with no manual clone. A prebuilt standalone binary
(no Python needed) is planned but, like the MCP image, is produced only by a versioned release,
so it isn't downloadable yet — install from git for now.

It reads the same env vars as the MCP server:

```bash
export KANBAN_API_URL=https://simple-kanban-jian.fly.dev
export KANBAN_TOKEN=kanban_pat_…
export KANBAN_BOARD_ID=1        # optional default board
```

**A CI pre-step.** `kan warmup` pings the health endpoint and needs no token, so it's the ideal
first step to wake the deploy before a batch of authenticated calls. It exits `0` once the API is
awake and `1` while it's still waking, so loop on it:

```bash
until kan warmup; do sleep 2; done   # block until the API is awake
kan list --column todo               # now the real work
```

The CLI uses distinct exit codes for scripting — `3` for `401`, `4` for `403`, `5` for `404` —
so a job can react to auth versus not-found without parsing text.

## Self-hosting

You self-host when you want an instance your team owns. It's the same single artifact as the
hosted board, so nothing here duplicates the ops docs — this is just the map.

**Locally**, from the repo root:

```bash
docker compose up -d db     # Postgres 17
# then the backend + frontend per the root README's Quick start
```

`docker-compose.yml` also defines the full app if you want it containerised. For a deployed
instance, [`fly.toml`](../../fly.toml) and the root [`Dockerfile`](../../Dockerfile) build and
run the single artifact on Fly.io with a Neon Postgres — the same setup behind the hosted board.
The [Developer Workflows playbook](../DEVELOPER-WORKFLOWS.md) covers the CI/CD and deploy machinery
in depth.

To enable GitHub login on your own instance, set `GITHUB_OAUTH_CLIENT_ID` and
`GITHUB_OAUTH_CLIENT_SECRET` (both unset → the board still boots, but login is unavailable). See
the Configuration section of [`CLAUDE.md`](../../CLAUDE.md) for the full env-var list, including
`AUTH_SECRET` and `COOKIE_SECURE`.

## Single-owner boards, and what that means today

Every board has exactly one owner. `/api/v1` is auth-required and owner-gated: a session or a PAT
resolves to a user, and that user can only see and change boards they own. **There is no board
sharing yet** — you can't invite a teammate onto your board, and an agent's PAT can never reach
boards owned by someone else. That's a deliberate current limit, with real collaboration left to a
future milestone.

So for more than one person or team right now, the honest answer is: each person uses their own
boards, or each team self-hosts its own instance. Point your agents at a board you own, and set
`KANBAN_BOARD_ID` so they stay on it.
