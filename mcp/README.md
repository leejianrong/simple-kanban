# Simple Kanban — MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the Simple Kanban
REST API (`/api/v1`) as tools an agent (e.g. Claude Code) can call. It is a thin
`httpx` wrapper — every tool maps to one endpoint — so the API stays the single
source of truth (API-first, ADR 0005). Milestone 2 slice **V5**.

## Tools

| Tool | Endpoint | Needs a write token? |
|------|----------|----------------------|
| `list_cards(column?, epic_id?, updated_since?, limit?, cursor?)` | `GET /cards` (V3 query API) | no |
| `get_card(card_id)` | `GET /cards/{id}` | no |
| `create_card(title, description?, column?, story_points?, assignee?, epic_id?)` | `POST /cards` | yes* |
| `create_epic(name, description?)` | `POST /epics` | yes* |
| `update_card(card_id, title?, description?, story_points?, assignee?, epic_id?)` | `PATCH /cards/{id}` | yes* |
| `move_card(card_id, column, position?)` | `POST /cards/{id}/move` | yes* |
| `delete_card(card_id)` | `DELETE /cards/{id}` | yes* |

\* A token was originally required **only** for writes, and only if the target
server had `API_TOKENS` set (ADR 0010). **Since M3 V8 (ADR 0013) the whole
`/api/v1` surface is auth-required** — reads *and* writes need a principal, so
`KANBAN_TOKEN` is now mandatory. **Two token options during the V8→V10 window:**

1. **A personal access token (recommended, V9 / ADR 0014).** Create one in the SPA
   (top-bar **Tokens** → *New token*), copy the `kanban_pat_…` secret shown once,
   and set it as `KANBAN_TOKEN`. It authenticates **as your user** and is
   **owner-gated** — the agent can only touch boards you own. No server config
   needed. This is the path V10 wires up fully (board targeting + create/list-board
   tools).
2. **A shared `API_TOKENS` service token (transitional).** Set `API_TOKENS` on the
   server and use one of its values as `KANBAN_TOKEN`; it resolves to an unscoped
   **SERVICE** principal that bypasses ownership. Removed in **V10** — prefer a PAT.

A fully tokenless server rejects the MCP with `401`.

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `KANBAN_API_URL` | `http://localhost:8000` | API origin (the `/api/v1` prefix is added for you) |
| `KANBAN_TOKEN` | *(unset)* | Bearer token (required since V8 — `/api/v1` is auth-required). Prefer a per-user **PAT** (`kanban_pat_…`, created in the Tokens UI, V9); an `API_TOKENS` value also works transitionally. Empty → `401` |

## Run it

Uses [`uv`](https://docs.astral.sh/uv/) like the backend (Python 3.12+):

```bash
cd mcp
uv sync                                   # install deps
KANBAN_API_URL=http://localhost:8000 uv run python -m kanban_mcp   # stdio server
```

It speaks MCP over **stdio**, so you normally don't run it by hand — a client
launches it. To smoke-test the tools without a client, run the test suite:

```bash
uv run pytest -q          # unit tests (mocked httpx) + a tool-list smoke test
```

## Wire it into Claude Code

Copy [`.mcp.json.example`](../.mcp.json.example) to `.mcp.json` at the repo root
and adjust the env. Claude Code discovers project-scoped servers there and will
ask you to approve it.

**Local dev** (tokenless backend on :8000):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "uv",
      "args": ["run", "--directory", "./mcp", "python", "-m", "kanban_mcp"],
      "env": { "KANBAN_API_URL": "http://localhost:8000", "KANBAN_TOKEN": "" }
    }
  }
}
```

**Production** (auth enabled — set the token to one listed in the server's
`API_TOKENS` Fly secret):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "uv",
      "args": ["run", "--directory", "./mcp", "python", "-m", "kanban_mcp"],
      "env": {
        "KANBAN_API_URL": "https://simple-kanban-jian.fly.dev",
        "KANBAN_TOKEN": "<one-of-your-API_TOKENS>"
      }
    }
  }
}
```

`--directory ./mcp` is relative to the repo root (where Claude Code launches it);
use an absolute path if you run the client from elsewhere. Once connected, ask
the agent to *"list the cards"* or *"create an epic and a couple of stories under
it, then move one to In Progress"* and watch them appear on the board.
