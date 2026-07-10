# Simple Kanban — MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the Simple Kanban
REST API (`/api/v1`) as tools an agent (e.g. Claude Code) can call. It is a thin
`httpx` wrapper — every tool maps to one endpoint — so the API stays the single
source of truth (API-first, ADR 0005). Milestone 2 slice **V5**; board-scoped in
**V10** (ADR 0015).

## Tools

| Tool | Endpoint | Board target |
|------|----------|--------------|
| `warmup()` | `GET /api/health` (unversioned) | — (wakes a scaled-to-zero server; soft status) |
| `list_boards()` | `GET /boards` | — (lists boards you own) |
| `create_board(name)` | `POST /boards` | — (creates one you own) |
| `get_board(board_id)` | `GET /boards/{id}` | — (by id) |
| `update_board(board_id, name?)` | `PATCH /boards/{id}` | via the entity's own board |
| `delete_board(board_id)` | `DELETE /boards/{id}` | via the entity's own board |
| `list_cards(board_id?, column?, epic_id?, updated_since?, limit?, cursor?)` | `GET /cards` (V3 query API) | `board_id` |
| `list_epics(board_id?)` | `GET /epics` | `board_id` |
| `get_card(card_id)` | `GET /cards/{id}` | — (by card id) |
| `get_epic(epic_id)` | `GET /epics/{id}` | — (by id) |
| `create_card(title, board_id?, description?, column?, story_points?, assignee?, epic_id?)` | `POST /cards` | `board_id` |
| `create_cards(cards)` | `POST /cards` × N (client-side loop) | per-card `board_id` |
| `create_epic(name, board_id?, description?)` | `POST /epics` | `board_id` |
| `update_epic(epic_id, name?, description?)` | `PATCH /epics/{id}` | via the entity's own board |
| `delete_epic(epic_id)` | `DELETE /epics/{id}` | via the entity's own board |
| `update_card(card_id, title?, description?, story_points?, assignee?, epic_id?)` | `PATCH /cards/{id}` | — (by card id) |
| `move_card(card_id, column, position?)` | `POST /cards/{id}/move` | — (by card id) |
| `claim_card(card_id, assignee)` | `POST /cards/{id}/move` + `PATCH /cards/{id}` | — (by card id) |
| `delete_card(card_id)` | `DELETE /cards/{id}` | — (by card id) |
| `add_dependency(card_id, blocker_id)` | `POST /cards/{id}/dependencies` | — (by card id) |
| `remove_dependency(card_id, blocker_id)` | `DELETE /cards/{id}/dependencies/{blocker_id}` | — (by card id) |
| `list_dependencies(card_id)` | `GET /cards/{id}` (shapes `blocked_by`/`blocks`) | — (by card id) |
| `add_link(card_id, label, url)` | `POST /cards/{id}/links` | — (by card id) |
| `remove_link(card_id, link_id)` | `DELETE /cards/{id}/links/{link_id}` | — (by card id) |
| `add_comment(card_id, body)` | `POST /cards/{id}/comments` | — (by card id) |
| `list_comments(card_id)` | `GET /cards/{id}/comments` (wraps in `comments`) | — (by card id) |

> Work-links (KAN-32) are also inlined on every card read — `list_cards`/`get_card`
> already return each card's `links` array — so `add_link`/`remove_link` are just the
> write path. Comments (KAN-33) are a thread, so they live behind `list_comments`
> rather than on the card body.

**Board scoping (V10, ADR 0015).** Call `list_boards` to discover the boards you
own, then target any of them per call:

- The board-scoped tools take an optional **`board_id`**. Omit it and the server
  uses **`KANBAN_BOARD_ID`** if set, else the API's own fallback (`list_*` = all
  your boards; `create_*` = your earliest board).
- Card-id-addressed tools (`get_card`/`update_card`/`move_card`/`delete_card`) need
  no `board_id` — the server authorizes via the card's own board.
- Access is bounded to boards **you** own: a `board_id` you don't own returns `403`
  ("that board isn't yours — call `list_boards`"). A bad/expired token returns
  `401` ("set `KANBAN_TOKEN` to a valid PAT").

**Authentication — a personal access token is required.** Since M3 V8 (ADR 0013)
the whole `/api/v1` surface is auth-required, and V10 (ADR 0015) removed the old
shared-`API_TOKENS` bypass. Create a **PAT** in the SPA (top-bar **Tokens** →
*New token*), copy the `kanban_pat_…` secret shown once, and set it as
`KANBAN_TOKEN`. It authenticates **as your user** and is **owner-gated** — the
agent can only touch boards you own. A tokenless (or bad-token) server rejects the
MCP with `401`.

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `KANBAN_API_URL` | `http://localhost:8000` | API origin (the `/api/v1` prefix is added for you) |
| `KANBAN_TOKEN` | *(unset)* | **Required.** A per-user **PAT** (`kanban_pat_…`, created in the Tokens UI, V9/ADR 0014). Empty → `401` |
| `KANBAN_BOARD_ID` | *(unset)* | Optional default board id for board-scoped tools when a call omits `board_id`. Unset → the API's fallback (list = all your boards; create = earliest) |

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
ask you to approve it. In both cases set `KANBAN_TOKEN` to a `kanban_pat_…` you
created in the SPA Tokens tab.

**Local dev** (backend on :8000):

```json
{
  "mcpServers": {
    "kanban": {
      "command": "uv",
      "args": ["run", "--directory", "./mcp", "python", "-m", "kanban_mcp"],
      "env": {
        "KANBAN_API_URL": "http://localhost:8000",
        "KANBAN_TOKEN": "kanban_pat_…",
        "KANBAN_BOARD_ID": "1"
      }
    }
  }
}
```

**Production:**

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

`KANBAN_BOARD_ID` pins the default board for calls that omit `board_id`; the
snippets above (and [`.mcp.json.example`](../.mcp.json.example)) preset it to `1`,
the seeded default board — **change it to your own board id** (from `list_boards`)
so the agent doesn't target the wrong board, or leave it empty to fall back to the
API default (list = all your boards, create = your earliest). `--directory ./mcp`
is relative to the repo root (where Claude Code launches it); use an absolute path
if you run the client from elsewhere. Once
connected, ask the agent to *"list my boards"*, then *"create an epic and a couple
of stories under it on board N, then move one to In Progress"* and watch them
appear on the board.
