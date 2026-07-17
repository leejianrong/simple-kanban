"""``kan`` — card / board / epic CRUD over the Simple Kanban API (KAN-22, KAN-23).

Framework choice: **stdlib ``argparse``** with subparsers. No new dependency —
consistent with the repo's thin ethos (the MCP server likewise leans on the SDK +
httpx and nothing else). ``typer``/``click`` would buy nicer help/colour but add a
dependency for a handful of subcommands; not worth it here.

Card verbs are top-level (``kan list``/``create``/…); boards and epics are nested
groups (``kan board list``, ``kan epic create``) so their verbs don't collide with
the card verbs — parity with the board/epic surface of ``/api/v1`` (KAN-23).

The CLI is a thin adapter over the shared ``KanbanClient``: parse args → env
config → one client call → print. ``--json`` prints the client's raw dict (for
``kan list --json | jq …``); otherwise a concise ``ticket  column  title`` line.

Exit codes (for scripting):
    0  success
    1  general / config / non-mapped API error
    2  usage error (argparse's own convention)
    3  401 unauthorized (bad/missing token)
    4  403 forbidden (board isn't yours)
    5  404 not found
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from kanban_client import KanbanApiError, KanbanClient

from .config import (
    DEFAULT_API_URL,
    Config,
    ConfigError,
    config_file_path,
    find_mcp_json,
    load_config,
    resolve_values,
    write_config_file,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2  # argparse's own convention; documented here for completeness.
EXIT_AUTH = 3
EXIT_FORBIDDEN = 4
EXIT_NOT_FOUND = 5

_STATUS_EXIT = {401: EXIT_AUTH, 403: EXIT_FORBIDDEN, 404: EXIT_NOT_FOUND}

COLUMNS = ("todo", "in_progress", "done")
PRIORITIES = ("none", "low", "medium", "high", "urgent")


# --- output helpers ---------------------------------------------------------


def _emit(result: Any, *, as_json: bool, noun: str = "card") -> None:
    """Print a command result: raw JSON when ``--json``, else a human summary.

    ``noun`` (``card``/``epic``/``board``) only disambiguates the delete summary,
    whose result dict (``{"deleted": id}``) is otherwise shape-identical across
    entities; everything else is detected from the result's shape.
    """
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return
    print(_humanize(result, noun=noun))


def _humanize(result: Any, *, noun: str = "card") -> str:
    """Render a client result as concise human text (one entity per line)."""
    if isinstance(result, dict) and "cards" in result:  # list_cards
        cards = result["cards"]
        if not cards:
            return "(no cards)"
        lines = [_card_line(c) for c in cards]
        if result.get("next_cursor"):
            lines.append(f"(more — next cursor: {result['next_cursor']})")
        return "\n".join(lines)
    if isinstance(result, dict) and "boards" in result:  # list_boards
        boards = result["boards"]
        return "\n".join(_board_line(b) for b in boards) if boards else "(no boards)"
    if isinstance(result, dict) and "epics" in result:  # list_epics
        epics = result["epics"]
        return "\n".join(_epic_line(e) for e in epics) if epics else "(no epics)"
    if isinstance(result, dict) and "labels" in result:  # list_labels
        labels = result["labels"]
        return "\n".join(_label_line(la) for la in labels) if labels else "(no labels)"
    if isinstance(result, dict) and "deleted" in result:  # delete_{card,epic,label}
        return f"deleted {noun} {result['deleted']}"
    if isinstance(result, dict) and "status" in result:  # warmup
        return _warmup_line(result)
    # A single label carries ``color`` (distinctive) — matched before the generic
    # name-without-title branch below.
    if isinstance(result, dict) and "color" in result and "name" in result:
        return _label_line(result)
    # A single entity: epics/boards carry ``name`` (no ``title``); cards carry
    # ``title``. Epics additionally have a ``ticket_number`` (``EPIC-…``).
    if isinstance(result, dict) and "name" in result and "title" not in result:
        return _epic_line(result) if "ticket_number" in result else _board_line(result)
    if isinstance(result, dict) and "ticket_number" in result:  # a single card
        return _card_line(result)
    return json.dumps(result, default=str)


def _card_line(card: dict[str, Any]) -> str:
    """One concise line for a card: ticket, column, title (tab-separated)."""
    return "\t".join(
        (
            str(card.get("ticket_number", card.get("id", "?"))),
            str(card.get("column", "")),
            str(card.get("title", "")),
        )
    )


def _epic_line(epic: dict[str, Any]) -> str:
    """One concise line for an epic: ticket, name (tab-separated)."""
    return "\t".join(
        (
            str(epic.get("ticket_number", epic.get("id", "?"))),
            str(epic.get("name", "")),
        )
    )


def _board_line(board: dict[str, Any]) -> str:
    """One concise line for a board: id, name (tab-separated)."""
    return "\t".join((str(board.get("id", "?")), str(board.get("name", ""))))


def _label_line(label: dict[str, Any]) -> str:
    """One concise line for a label: id, name, color (tab-separated)."""
    return "\t".join(
        (
            str(label.get("id", "?")),
            str(label.get("name", "")),
            str(label.get("color", "")),
        )
    )


def _warmup_line(result: dict[str, Any]) -> str:
    """One concise line for a warmup result: the status, plus any detail.

    ``ok`` → the API is awake; ``waking``/``error`` carry a ``detail`` explaining
    what to do next (call again shortly / what failed)."""
    status = str(result.get("status", "?"))
    if status == "ok":
        return "ok\tAPI is awake"
    detail = result.get("detail")
    return f"{status}\t{detail}" if detail else status


# --- board resolution -------------------------------------------------------


def _resolve_board(arg_board: int | None, config: Config) -> int | None:
    """The per-call ``--board`` wins, else ``KANBAN_BOARD_ID``, else None (let the
    API apply its own fallback). Mirrors the MCP server's ``_board`` helper."""
    return arg_board if arg_board is not None else config.board_id


# --- command handlers -------------------------------------------------------
# Each returns the client's result dict; printing + exit codes are handled centrally.


def _cmd_list(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.list_cards(
        board_id=_resolve_board(args.board, config),
        column=args.column,
        epic_id=args.epic,
        priority=args.priority,
        label=args.label,
        due_before=args.due_before,
        overdue=args.overdue or None,
        limit=args.limit,
    )


def _cmd_get(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.get_card(args.card_id)


def _cmd_create(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.create_card(
        args.title,
        board_id=_resolve_board(args.board, config),
        description=args.description,
        column=args.column,
        story_points=args.points,
        assignee=args.assignee,
        epic_id=args.epic,
        priority=args.priority,
        due_date=args.due,
        label_ids=args.label or None,
    )


def _cmd_update(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.update_card(
        args.card_id,
        title=args.title,
        description=args.description,
        story_points=args.points,
        assignee=args.assignee,
        epic_id=args.epic,
        priority=args.priority,
        due_date=args.due,
        label_ids=args.label if args.label is not None else None,
    )


def _cmd_move(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.move_card(args.card_id, args.column, position=args.position)


def _cmd_delete(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    if not args.yes:
        raise ConfigError(
            f"refusing to delete card {args.card_id} without confirmation; pass --yes"
        )
    return client.delete_card(args.card_id)


# --- ops handlers -----------------------------------------------------------


def _cmd_warmup(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    # The shared client's warmup() pings the public /api/health, rides a cold
    # start via the shared retry/timeout, and never throws — it returns a status
    # dict the caller maps to an exit code (see run()).
    return client.warmup()


# --- board handlers ---------------------------------------------------------
# Boards are owner-scoped, not board-scoped: no --board targeting here.


def _cmd_board_list(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.list_boards()


def _cmd_board_create(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.create_board(args.name)


# --- epic handlers ----------------------------------------------------------
# Epics are board-scoped, so list/create honour --board / KANBAN_BOARD_ID.


def _cmd_epic_list(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.list_epics(board_id=_resolve_board(args.board, config))


def _cmd_epic_create(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.create_epic(
        args.name,
        board_id=_resolve_board(args.board, config),
        description=args.description,
    )


def _cmd_epic_update(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.update_epic(
        args.epic_id,
        name=args.name,
        description=args.description,
    )


def _cmd_epic_delete(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    if not args.yes:
        raise ConfigError(
            f"refusing to delete epic {args.epic_id} without confirmation; pass --yes"
        )
    return client.delete_epic(args.epic_id)


# --- label handlers ---------------------------------------------------------
# Labels are board-scoped: list/create honour --board / KANBAN_BOARD_ID; delete
# is addressed by the label's own id (authorized via its board).


def _cmd_label_list(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    board = _resolve_board(args.board, config)
    if board is None:
        raise ConfigError("a board is required; pass --board or set KANBAN_BOARD_ID")
    return client.list_labels(board)


def _cmd_label_create(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    board = _resolve_board(args.board, config)
    if board is None:
        raise ConfigError("a board is required; pass --board or set KANBAN_BOARD_ID")
    return client.create_label(board, args.name, args.color)


def _cmd_label_delete(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    if not args.yes:
        raise ConfigError(
            f"refusing to delete label {args.label_id} without confirmation; pass --yes"
        )
    return client.delete_label(args.label_id)


# --- config handlers (local: no client, no network) -------------------------
# These operate on local config only, so ``run()`` dispatches them via
# ``local_func`` before building a KanbanClient (and before any token is required).


def _redact_token(token: str) -> str:
    """Never print a usable token. Show only that one is set + its last 4 chars so
    a human can tell which PAT is in effect without exposing it."""
    if not token:
        return "(unset)"
    tail = token[-4:] if len(token) > 4 else ""
    return f"set (…{tail})"


def _cmd_config_path(args: argparse.Namespace) -> int:
    print(config_file_path())
    return EXIT_OK


def _cmd_config_show(args: argparse.Namespace) -> int:
    """Print the *effective* config after the env → file → .mcp.json chain, with
    the token redacted. Handy for 'why is kan hitting the wrong board?'."""
    resolved = resolve_values()
    mcp = find_mcp_json()
    out = {
        "api_url": resolved.get("api_url") or DEFAULT_API_URL,
        "token": _redact_token(resolved.get("token", "")),
        "board_id": resolved.get("board_id"),
        "config_file": str(config_file_path()),
        "mcp_json": str(mcp) if mcp else None,
    }
    if getattr(args, "as_json", False):
        print(json.dumps(out, indent=2))
    else:
        for key, val in out.items():
            print(f"{key}\t{val}")
    return EXIT_OK


def _validate_board_id_arg(raw: str | None) -> None:
    if raw is not None and raw.strip() and not raw.strip().lstrip("-").isdigit():
        raise ConfigError(f"--board-id must be an integer, got {raw!r}")


def _cmd_config_set(args: argparse.Namespace) -> int:
    """Write api_url/board_id/token to the user config file (0600). ``--token-stdin``
    reads the PAT from stdin so it never lands in argv / shell history."""
    _validate_board_id_arg(args.board_id)
    token: str | None = None
    if getattr(args, "token_stdin", False):
        token = sys.stdin.readline().strip()
        if not token:
            print("kan: no token read from stdin", file=sys.stderr)
            return EXIT_ERROR
    elif args.token is not None:
        token = args.token
    if args.api_url is None and args.board_id is None and token is None:
        print(
            "kan: nothing to set (pass --api-url / --board-id / --token[-stdin])",
            file=sys.stderr,
        )
        return EXIT_ERROR
    path = write_config_file(api_url=args.api_url, token=token, board_id=args.board_id)
    print(f"wrote {path}")
    return EXIT_OK


def _cmd_login(args: argparse.Namespace) -> int:
    """Save a PAT to the config file. Prompts (hidden) on a TTY, else reads one line
    from stdin — so the token never appears on the command line."""
    _validate_board_id_arg(args.board_id)
    if getattr(args, "token_stdin", False) or not sys.stdin.isatty():
        token = sys.stdin.readline().strip()
    else:
        import getpass

        token = getpass.getpass("Paste your Kanban PAT (kanban_pat_…): ").strip()
    if not token:
        print("kan: no token provided", file=sys.stderr)
        return EXIT_ERROR
    path = write_config_file(api_url=args.api_url, token=token, board_id=args.board_id)
    print(f"saved token to {path} (mode 0600)")
    return EXIT_OK


# --- argument parser --------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kan",
        description="Manage Simple Kanban cards, boards, and epics from the command line.",
        epilog=(
            "Configuration keys (api_url / token / board_id), resolved per value in\n"
            "this order — first non-empty wins:\n"
            "  1. env vars   KANBAN_API_URL / KANBAN_TOKEN / KANBAN_BOARD_ID\n"
            "  2. config file  ~/.config/kan/config.toml  (see `kan login` / `kan config`)\n"
            "  3. .mcp.json    nearest up the tree, .mcpServers.kanban.env.*\n"
            "So the PAT can stay in a file and never touch the command line. Run\n"
            "`kan login` once to save it; `kan config show` prints the effective config.\n"
            "\n"
            "Exit codes: 0 ok, 1 error, 2 usage, 3 unauthorized, 4 forbidden, 5 not found."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # A shared parent so --json works before OR after the subcommand
    # (e.g. `kan --json list` and `kan list --json` both parse).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        # SUPPRESS so an absent subcommand-level --json does not clobber a global
        # `kan --json <cmd>` already parsed by the main parser below.
        default=argparse.SUPPRESS,
        help="print the raw JSON from the API (for piping, e.g. | jq)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        default=False,
        help=argparse.SUPPRESS,
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    # ``warmup`` pings the public /api/health to wake a scaled-to-zero Fly+Neon
    # deploy before a batch of work (handy as a CI pre-step). It needs no token
    # (require_token=False) and maps its non-throwing status to an exit code
    # (is_warmup=True): 0 when awake, 1 while still waking / on error.
    p_warmup = sub.add_parser(
        "warmup",
        parents=[common],
        help="wake the API (ping /api/health) before a batch of work",
    )
    p_warmup.set_defaults(func=_cmd_warmup, require_token=False, is_warmup=True)

    p_list = sub.add_parser("list", parents=[common], help="list / query cards")
    p_list.add_argument("--board", type=int, help="board id (default: KANBAN_BOARD_ID)")
    p_list.add_argument("--column", choices=COLUMNS, help="filter by column")
    p_list.add_argument("--epic", type=int, metavar="EPIC_ID", help="filter by epic id")
    p_list.add_argument("--priority", choices=PRIORITIES, help="filter by priority")
    p_list.add_argument("--label", type=int, metavar="LABEL_ID", help="filter by label id")
    p_list.add_argument(
        "--due-before", dest="due_before", metavar="ISO",
        help="only cards due strictly before this ISO-8601 timestamp",
    )
    p_list.add_argument(
        "--overdue", action="store_true", help="only past-due cards not yet done"
    )
    p_list.add_argument("--limit", type=int, help="max cards to return")
    p_list.set_defaults(func=_cmd_list)

    p_get = sub.add_parser("get", parents=[common], help="get a single card by id")
    p_get.add_argument("card_id", type=int)
    p_get.set_defaults(func=_cmd_get)

    p_create = sub.add_parser("create", parents=[common], help="create a card")
    p_create.add_argument("title")
    p_create.add_argument("--board", type=int, help="board id (default: KANBAN_BOARD_ID)")
    p_create.add_argument("--description")
    p_create.add_argument("--column", choices=COLUMNS, help="starting column (default: todo)")
    p_create.add_argument("--points", type=int, metavar="N", help="story points (1/2/3/5/8/13)")
    p_create.add_argument("--assignee")
    p_create.add_argument("--epic", type=int, metavar="EPIC_ID", help="link to an epic")
    p_create.add_argument("--priority", choices=PRIORITIES, help="priority (default: none)")
    p_create.add_argument("--due", metavar="ISO", help="due date (ISO-8601 timestamp)")
    p_create.add_argument(
        "--label", type=int, action="append", metavar="LABEL_ID",
        help="attach a label by id (repeatable)",
    )
    p_create.set_defaults(func=_cmd_create)

    p_update = sub.add_parser("update", parents=[common], help="edit a card's fields")
    p_update.add_argument("card_id", type=int)
    p_update.add_argument("--title")
    p_update.add_argument("--description")
    p_update.add_argument("--points", type=int, metavar="N", help="story points (1/2/3/5/8/13)")
    p_update.add_argument("--assignee")
    p_update.add_argument(
        "--epic", type=int, metavar="EPIC_ID", help="link to an epic (by id)"
    )
    p_update.add_argument("--priority", choices=PRIORITIES, help="re-rank priority")
    p_update.add_argument("--due", metavar="ISO", help="due date (ISO-8601 timestamp)")
    p_update.add_argument(
        "--label", type=int, action="append", metavar="LABEL_ID",
        help="replace the card's labels with these ids (repeatable; omit to leave unchanged)",
    )
    p_update.set_defaults(func=_cmd_update)

    p_move = sub.add_parser("move", parents=[common], help="move a card to a column")
    p_move.add_argument("card_id", type=int)
    p_move.add_argument("column", choices=COLUMNS)
    p_move.add_argument("--position", type=int, help="index within the column (default: append)")
    p_move.set_defaults(func=_cmd_move)

    p_delete = sub.add_parser("delete", parents=[common], help="delete a card")
    p_delete.add_argument("card_id", type=int)
    p_delete.add_argument("--yes", action="store_true", help="confirm the deletion")
    p_delete.set_defaults(func=_cmd_delete)

    # --- board subcommands (nested group; parity with /api/v1/boards) --------
    p_board = sub.add_parser("board", help="manage boards (list / create)")
    board_sub = p_board.add_subparsers(
        dest="board_command", metavar="<subcommand>", required=True
    )

    p_board_list = board_sub.add_parser("list", parents=[common], help="list your boards")
    p_board_list.set_defaults(func=_cmd_board_list, noun="board")

    p_board_create = board_sub.add_parser("create", parents=[common], help="create a board")
    p_board_create.add_argument("name")
    p_board_create.set_defaults(func=_cmd_board_create, noun="board")

    # --- epic subcommands (nested group; parity with /api/v1/epics) ----------
    p_epic = sub.add_parser("epic", help="manage epics (list / create / update / delete)")
    epic_sub = p_epic.add_subparsers(
        dest="epic_command", metavar="<subcommand>", required=True
    )

    p_epic_list = epic_sub.add_parser("list", parents=[common], help="list / query epics")
    p_epic_list.add_argument("--board", type=int, help="board id (default: KANBAN_BOARD_ID)")
    p_epic_list.set_defaults(func=_cmd_epic_list, noun="epic")

    p_epic_create = epic_sub.add_parser("create", parents=[common], help="create an epic")
    p_epic_create.add_argument("name")
    p_epic_create.add_argument("--board", type=int, help="board id (default: KANBAN_BOARD_ID)")
    p_epic_create.add_argument("--description")
    p_epic_create.set_defaults(func=_cmd_epic_create, noun="epic")

    p_epic_update = epic_sub.add_parser("update", parents=[common], help="edit an epic's fields")
    p_epic_update.add_argument("epic_id", type=int)
    p_epic_update.add_argument("--name")
    p_epic_update.add_argument("--description")
    p_epic_update.set_defaults(func=_cmd_epic_update, noun="epic")

    p_epic_delete = epic_sub.add_parser("delete", parents=[common], help="delete an epic")
    p_epic_delete.add_argument("epic_id", type=int)
    p_epic_delete.add_argument("--yes", action="store_true", help="confirm the deletion")
    p_epic_delete.set_defaults(func=_cmd_epic_delete, noun="epic")

    # --- label subcommands (nested group; parity with /api/v1 labels) --------
    p_label = sub.add_parser("label", help="manage labels (list / create / delete)")
    label_sub = p_label.add_subparsers(
        dest="label_command", metavar="<subcommand>", required=True
    )

    p_label_list = label_sub.add_parser("list", parents=[common], help="list a board's labels")
    p_label_list.add_argument("--board", type=int, help="board id (default: KANBAN_BOARD_ID)")
    p_label_list.set_defaults(func=_cmd_label_list, noun="label")

    p_label_create = label_sub.add_parser("create", parents=[common], help="create a label")
    p_label_create.add_argument("name")
    p_label_create.add_argument("color", help="a color string, e.g. a hex like #0ea5e9")
    p_label_create.add_argument("--board", type=int, help="board id (default: KANBAN_BOARD_ID)")
    p_label_create.set_defaults(func=_cmd_label_create, noun="label")

    p_label_delete = label_sub.add_parser("delete", parents=[common], help="delete a label")
    p_label_delete.add_argument("label_id", type=int)
    p_label_delete.add_argument("--yes", action="store_true", help="confirm the deletion")
    p_label_delete.set_defaults(func=_cmd_label_delete, noun="label")

    # --- login / config (local: no token, no network) ------------------------
    # ``login`` saves a PAT to ~/.config/kan/config.toml without it touching argv:
    # a hidden prompt on a TTY, else one line from stdin.
    p_login = sub.add_parser(
        "login",
        parents=[common],
        help="save your PAT to the config file (prompts; never on the command line)",
    )
    p_login.add_argument("--api-url", help="also save the API origin")
    p_login.add_argument("--board-id", help="also save a default board id")
    p_login.add_argument(
        "--token-stdin",
        action="store_true",
        help="read the token from stdin instead of prompting (e.g. `… | kan login --token-stdin`)",
    )
    p_login.set_defaults(local_func=_cmd_login)

    p_config = sub.add_parser("config", help="inspect / set the config file (set / show / path)")
    config_sub = p_config.add_subparsers(
        dest="config_command", metavar="<subcommand>", required=True
    )

    p_config_set = config_sub.add_parser(
        "set", parents=[common], help="write api_url / board_id / token to the config file"
    )
    p_config_set.add_argument("--api-url")
    p_config_set.add_argument("--board-id")
    token_grp = p_config_set.add_mutually_exclusive_group()
    token_grp.add_argument(
        "--token", help="the PAT (discouraged — ends up in shell history; prefer --token-stdin)"
    )
    token_grp.add_argument(
        "--token-stdin", action="store_true", help="read the PAT from stdin (keeps it out of argv)"
    )
    p_config_set.set_defaults(local_func=_cmd_config_set)

    p_config_show = config_sub.add_parser(
        "show", parents=[common], help="print the effective config (token redacted)"
    )
    p_config_show.set_defaults(local_func=_cmd_config_show)

    p_config_path = config_sub.add_parser(
        "path", parents=[common], help="print the config file path"
    )
    p_config_path.set_defaults(local_func=_cmd_config_path)

    return parser


# --- entry point ------------------------------------------------------------


def run(argv: Sequence[str] | None = None) -> int:
    """Parse args, dispatch, print, and return an exit code (no ``sys.exit``)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Local commands (login / config …) touch only the config file — no token, no
    # client, no network. Dispatch them before resolving or requiring config.
    local_func = getattr(args, "local_func", None)
    if local_func is not None:
        try:
            return local_func(args)
        except ConfigError as exc:
            print(f"kan: {exc}", file=sys.stderr)
            return EXIT_ERROR

    try:
        # warmup hits the public /api/health, so it doesn't need a token.
        config = load_config(require_token=getattr(args, "require_token", True))
    except ConfigError as exc:
        print(f"kan: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        with KanbanClient(config.api_url, config.token) as client:
            result = args.func(client, config, args)
    except ConfigError as exc:  # e.g. delete without --yes
        print(f"kan: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KanbanApiError as exc:
        print(f"kan: {exc}", file=sys.stderr)
        return _STATUS_EXIT.get(exc.status_code, EXIT_ERROR)
    except Exception as exc:  # network/timeout/unexpected — keep it clean for scripts
        print(f"kan: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # ``noun`` defaults to "card" (card verbs are top-level and set no noun);
    # the board/epic subparsers set it so the delete summary reads correctly.
    _emit(result, as_json=args.as_json, noun=getattr(args, "noun", "card"))
    # warmup never throws (a still-waking/failed server is a status, not an
    # exception), so it maps that status to a scripting-friendly exit code:
    # 0 when awake, 1 otherwise (retry the CI pre-step / investigate).
    if getattr(args, "is_warmup", False):
        return EXIT_OK if result.get("status") == "ok" else EXIT_ERROR
    return EXIT_OK
