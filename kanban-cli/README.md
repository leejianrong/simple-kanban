# Simple Kanban — `kan` CLI

A command-line client for the Simple Kanban REST API (`/api/v1`). Like the
[MCP server](../mcp/README.md), it is a thin adapter over the shared
[`kanban-client`](../kanban-client/) package — every subcommand maps to one API
call — so the API stays the single source of truth (API-first, ADR 0005).
Milestone 2 follow-on; card commands **KAN-22**, board + epic commands
**KAN-23**, packaging + this README + the CI job **KAN-24**.

It uses only the standard library's `argparse` (no `click`/`typer`) — consistent
with the repo's thin ethos.

## Commands

Card verbs are top-level; boards and epics are nested groups so their verbs don't
collide with the card verbs (parity with the `/api/v1` surface).

| Command | Endpoint |
|---------|----------|
| `kan list [--board N] [--column C] [--epic ID] [--limit N] [--json]` | `GET /cards` (V3 query API) |
| `kan get <card_id> [--json]` | `GET /cards/{id}` |
| `kan create <title> [--board N] [--description D] [--column C] [--points N] [--assignee A] [--epic ID] [--json]` | `POST /cards` |
| `kan update <card_id> [--title T] [--description D] [--points N] [--assignee A] [--epic ID] [--json]` | `PATCH /cards/{id}` |
| `kan move <card_id> <column> [--position N] [--json]` | `POST /cards/{id}/move` |
| `kan delete <card_id> --yes [--json]` | `DELETE /cards/{id}` |
| `kan board list [--json]` | `GET /boards` |
| `kan board create <name> [--json]` | `POST /boards` |
| `kan epic list [--board N] [--json]` | `GET /epics` |
| `kan epic create <name> [--board N] [--description D] [--json]` | `POST /epics` |
| `kan epic update <epic_id> [--name N] [--description D] [--json]` | `PATCH /epics/{id}` |
| `kan epic delete <epic_id> --yes [--json]` | `DELETE /epics/{id}` |
| `kan warmup [--json]` | `GET /api/health` |

Valid columns are `todo`, `in_progress`, `done`. `delete` requires `--yes` as a
guard against accidental destruction.

`kan warmup` pings the public health endpoint to wake a scaled-to-zero Fly + Neon
deploy (the first request after idle is slow — a documented cold start), riding it
out via the shared client's cold-start retry/timeout. Handy as a **CI pre-step**
before a batch of `kan` calls so the wake cost is paid once. It needs **no
`KANBAN_TOKEN`** (health is unauthenticated) and exits `0` once the API is awake,
`1` while it's still waking or on error — so a CI step can loop until it succeeds:

```bash
until kan warmup; do sleep 2; done   # block until the API is awake
```

Every command takes `--json` to print the API's raw response (for piping, e.g.
`kan list --json | jq`); without it you get a concise tab-separated summary
(`ticket  column  title` for cards, `ticket  name` for epics, `id  name` for
boards) suitable for `grep`/`cut`.

Run `kan --help`, `kan <command> --help`, `kan board --help`, or
`kan epic --help` for the full option list.

### Exit codes (for scripting)

| Code | Meaning |
|------|---------|
| `0` | success |
| `1` | general / config / non-mapped API error |
| `2` | usage error (argparse convention) |
| `3` | `401` unauthorized (bad/missing token) |
| `4` | `403` forbidden (board isn't yours) |
| `5` | `404` not found |

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `KANBAN_API_URL` | `http://localhost:8000` | API origin (the `/api/v1` prefix is added for you) |
| `KANBAN_TOKEN` | *(unset)* | **Required.** A per-user **PAT** (`kanban_pat_…`, created in the SPA top-bar **Tokens** tab, V9/ADR 0014). Empty/unset → a clean error before any request |
| `KANBAN_BOARD_ID` | *(unset)* | Optional default board id for board-scoped commands (`list`/`create`, `epic list`/`epic create`) when they omit `--board`. Unset → the API's fallback (list = all your boards; create = your earliest) |

**Authentication — a personal access token is required.** Since M3 V8 (ADR 0013)
the whole `/api/v1` surface is auth-required, and V10 (ADR 0015) removed the old
shared-`API_TOKENS` bypass. Create a **PAT** in the SPA (top-bar **Tokens** →
*New token*), copy the `kanban_pat_…` secret shown once, and set it as
`KANBAN_TOKEN`. It authenticates **as your user** and is **owner-gated** — the CLI
can only touch boards you own. A `board_id` you don't own returns exit `4`
(`403`); a bad/missing token returns exit `3` (`401`).

## Install

The CLI depends on the sibling `kanban-client` package by **path**
(`../kanban-client`, see `[tool.uv.sources]` in `pyproject.toml`), which shapes
the realistic install options.

**From a checkout (supported):**

```bash
git clone https://github.com/leejianrong/simple-kanban.git
cd simple-kanban
uv tool install ./kanban-cli        # installs the `kan` command on your PATH
```

`uv tool install` resolves the `../kanban-client` path source relative to the
checkout, so this works cleanly. Uninstall with `uv tool uninstall
simple-kanban-cli`.

**From git directly (supported):**

```bash
uv tool install "git+https://github.com/leejianrong/simple-kanban.git#subdirectory=kanban-cli"
```

`uv` clones the repo and resolves the sibling `../kanban-client` path source from
the **same** git checkout, so this installs `kan` without a manual clone
(verified). Uninstall the same way (`uv tool uninstall simple-kanban-cli`).

**During development**, skip the install and run from `kanban-cli/`:

```bash
cd kanban-cli
uv sync                              # install deps (incl. the dev group)
uv run kan --help                    # run without installing
```

> A standalone, no-Python single binary is planned (KAN-46) for a zero-install
> path; until then the checkout install above is the supported route.

## Usage examples

```bash
export KANBAN_API_URL=http://localhost:8000
export KANBAN_TOKEN=kanban_pat_…      # from the SPA Tokens tab
export KANBAN_BOARD_ID=1              # optional default board

kan board list                        # discover your boards
kan create "Wire up CI" --column todo --points 3
kan list --column in_progress
kan list --json | jq '.cards[].title'
kan move 12 done
kan epic create "Onboarding" --description "New-user flow"
kan delete 12 --yes
```

## Develop / test

Uses [`uv`](https://docs.astral.sh/uv/) like the rest of the repo (Python 3.12+).
Run from `kanban-cli/`:

```bash
uv sync                # install deps (incl. dev group)
uv run ruff check .    # lint (matches the CI `cli` job)
uv run pytest -q       # unit tests — mocked httpx + argparse dispatch, no DB
```

The tests mock the shared `KanbanClient`, so no backend or database is needed. CI
runs this as the `cli` job (see `.github/workflows/ci.yml`), mirroring the `mcp`
and `client` jobs.
