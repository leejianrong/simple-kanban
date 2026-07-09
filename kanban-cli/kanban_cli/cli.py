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

from .config import Config, ConfigError, load_config

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2  # argparse's own convention; documented here for completeness.
EXIT_AUTH = 3
EXIT_FORBIDDEN = 4
EXIT_NOT_FOUND = 5

_STATUS_EXIT = {401: EXIT_AUTH, 403: EXIT_FORBIDDEN, 404: EXIT_NOT_FOUND}

COLUMNS = ("todo", "in_progress", "done")


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
    if isinstance(result, dict) and "deleted" in result:  # delete_{card,epic}
        return f"deleted {noun} {result['deleted']}"
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
    )


def _cmd_update(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.update_card(
        args.card_id,
        title=args.title,
        description=args.description,
        story_points=args.points,
        assignee=args.assignee,
        epic_id=args.epic,
    )


def _cmd_move(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    return client.move_card(args.card_id, args.column, position=args.position)


def _cmd_delete(client: KanbanClient, config: Config, args: argparse.Namespace) -> Any:
    if not args.yes:
        raise ConfigError(
            f"refusing to delete card {args.card_id} without confirmation; pass --yes"
        )
    return client.delete_card(args.card_id)


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


# --- argument parser --------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kan",
        description="Manage Simple Kanban cards from the command line.",
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

    p_list = sub.add_parser("list", parents=[common], help="list / query cards")
    p_list.add_argument("--board", type=int, help="board id (default: KANBAN_BOARD_ID)")
    p_list.add_argument("--column", choices=COLUMNS, help="filter by column")
    p_list.add_argument("--epic", type=int, metavar="EPIC_ID", help="filter by epic id")
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

    return parser


# --- entry point ------------------------------------------------------------


def run(argv: Sequence[str] | None = None) -> int:
    """Parse args, dispatch, print, and return an exit code (no ``sys.exit``)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config()
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
    return EXIT_OK
