"""MCP server exposing the Simple Kanban API as agent tools (stdio transport).

Each tool is a thin wrapper over one ``/api/v1`` endpoint via ``KanbanClient``.
Type hints + docstrings here become the tool schema + description the agent sees
(FastMCP). Since M3 V8 (ADR 0013) ``/api/v1`` is auth-required, so ``KANBAN_TOKEN``
must be a valid personal access token (V9/ADR 0014); it authenticates as its
owning user and can only reach boards that user owns.

**Board scoping (V10, ADR 0015):** the agent works across multiple boards
dynamically. ``list_boards``/``create_board`` discover and make boards; the
board-scoped tools take an optional per-call ``board_id`` (defaulting to
``KANBAN_BOARD_ID`` when set, else the API's own fallback — list = all your
boards, create = your earliest board). Card-id-addressed tools
(``get_card``/``update_card``/``move_card``/``delete_card``) need no ``board_id``:
the server authorizes via the card's own board.

Run with ``python -m kanban_mcp`` (or the ``kanban-mcp`` script); Claude Code
launches it over stdio per the .mcp.json snippet in the README.
"""
from __future__ import annotations

from typing import Any, Literal

from kanban_client import KanbanClient
from mcp.server.fastmcp import FastMCP

from .config import load_config

Column = Literal["todo", "in_progress", "done"]

mcp = FastMCP("kanban")

_client: KanbanClient | None = None
_default_board_id: int | None = None


def _client_instance() -> KanbanClient:
    """Lazily build the API client from the environment on first tool use."""
    global _client, _default_board_id
    if _client is None:
        config = load_config()
        _client = KanbanClient(config.api_url, config.token)
        _default_board_id = config.board_id
    return _client


def _board(board_id: int | None) -> int | None:
    """Resolve the target board: the per-call ``board_id`` wins, else the
    ``KANBAN_BOARD_ID`` default, else ``None`` (let the API apply its fallback)."""
    return board_id if board_id is not None else _default_board_id


# --- ops: warmup ------------------------------------------------------------


@mcp.tool()
def warmup() -> dict[str, Any]:
    """Wake the API if it has scaled to zero (Fly free tier). Pings the health
    endpoint using the shared cold-start retry/timeout and returns a status
    without throwing: ``{"status": "ok", ...}`` once healthy, ``{"status":
    "waking", ...}`` if it's still coming up (call again shortly), or ``{"status":
    "error", ...}``. Call this before a burst of work to absorb the cold start in
    one place instead of on your first real tool call.
    """
    return _client_instance().warmup()


# --- boards: discover + create (V10) ---------------------------------------


@mcp.tool()
def list_boards() -> dict[str, Any]:
    """List the boards you own (id + name). Call this first to discover which
    boards you can target with ``board_id`` on the other tools."""
    return _client_instance().list_boards()


@mcp.tool()
def create_board(name: str) -> dict[str, Any]:
    """Create a new board owned by you; returns it (including its id)."""
    return _client_instance().create_board(name)


@mcp.tool()
def get_board(board_id: int) -> dict[str, Any]:
    """Fetch a single board by its numeric id (id + name). Authorized via the
    board's own id — you must own it."""
    return _client_instance().get_board(board_id)


@mcp.tool()
def update_board(board_id: int, name: str | None = None) -> dict[str, Any]:
    """Rename a board (only the arguments you pass are changed). Authorized via
    the board's own id — you must own it."""
    return _client_instance().update_board(board_id, name=name)


@mcp.tool()
def delete_board(board_id: int) -> dict[str, Any]:
    """Delete a board by id; its cards + epics cascade away. Authorized via the
    board's own id — you must own it."""
    return _client_instance().delete_board(board_id)


# --- cards + epics (board-scoped) ------------------------------------------


@mcp.tool()
def list_cards(
    board_id: int | None = None,
    column: Column | None = None,
    epic_id: int | None = None,
    updated_since: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List/query stories. ``board_id`` targets one board (defaults to
    KANBAN_BOARD_ID; omit both to span all your boards). Other filters (AND-ed):
    column, epic_id, and updated_since (an ISO-8601 timestamp — stories changed
    at/after it). Paginate with limit; if more results remain the response
    includes ``next_cursor`` to pass back as ``cursor``.
    """
    return _client_instance().list_cards(
        board_id=_board(board_id),
        column=column,
        epic_id=epic_id,
        updated_since=updated_since,
        limit=limit,
        cursor=cursor,
    )


@mcp.tool()
def list_epics(board_id: int | None = None) -> dict[str, Any]:
    """List epics. ``board_id`` targets one board (defaults to KANBAN_BOARD_ID;
    omit both to span all your boards)."""
    return _client_instance().list_epics(board_id=_board(board_id))


@mcp.tool()
def get_card(card_id: int) -> dict[str, Any]:
    """Fetch a single story by its numeric id."""
    return _client_instance().get_card(card_id)


@mcp.tool()
def get_epic(epic_id: int) -> dict[str, Any]:
    """Fetch a single epic by its numeric id. Authorized via the epic's own
    board — no ``board_id`` needed."""
    return _client_instance().get_epic(epic_id)


@mcp.tool()
def create_card(
    title: str,
    board_id: int | None = None,
    description: str | None = None,
    column: Column | None = None,
    story_points: int | None = None,
    assignee: str | None = None,
    epic_id: int | None = None,
) -> dict[str, Any]:
    """Create a story. Only ``title`` is required; it lands at the end of its
    column (default ``todo``). ``board_id`` targets one board (defaults to
    KANBAN_BOARD_ID; omit both to use your earliest board). ``story_points`` must
    be one of 1/2/3/5/8/13. ``epic_id`` links it to an existing epic on the same
    board.
    """
    return _client_instance().create_card(
        title,
        board_id=_board(board_id),
        description=description,
        column=column,
        story_points=story_points,
        assignee=assignee,
        epic_id=epic_id,
    )


@mcp.tool()
def create_cards(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Batch-create several stories in one call — hand it a list of card objects,
    each with the same fields as ``create_card`` (``title`` required; optional
    ``board_id``/``description``/``column``/``story_points``/``assignee``/
    ``epic_id``). Ideal for filing a whole epic's worth of stories at once: one
    tool call over a warm connection instead of N. A card that omits ``board_id``
    falls back to KANBAN_BOARD_ID (then the API default), same as ``create_card``.
    Returns ``{"created": [<card>, ...]}`` in the order given.

    **Fail-fast, not atomic:** if one card is rejected (e.g. a bad ``story_points``)
    the call errors and the cards created *before* it stay created — resubmit only
    the remainder.
    """
    resolved = []
    for card in cards:
        merged = dict(card)
        merged["board_id"] = _board(merged.get("board_id"))
        resolved.append(merged)
    return _client_instance().create_cards(resolved)


@mcp.tool()
def create_epic(
    name: str, board_id: int | None = None, description: str | None = None
) -> dict[str, Any]:
    """Create an epic (a per-board grouping stories can link to via epic_id).
    ``board_id`` targets one board (defaults to KANBAN_BOARD_ID; omit both to use
    your earliest board).
    """
    return _client_instance().create_epic(
        name, board_id=_board(board_id), description=description
    )


@mcp.tool()
def update_card(
    card_id: int,
    title: str | None = None,
    description: str | None = None,
    story_points: int | None = None,
    assignee: str | None = None,
    epic_id: int | None = None,
) -> dict[str, Any]:
    """Edit a story's fields (only the arguments you pass are changed). Use
    move_card to change column/position, not this. Authorized via the card's own
    board — no ``board_id`` needed.
    """
    return _client_instance().update_card(
        card_id,
        title=title,
        description=description,
        story_points=story_points,
        assignee=assignee,
        epic_id=epic_id,
    )


@mcp.tool()
def move_card(card_id: int, column: Column, position: int | None = None) -> dict[str, Any]:
    """Move a story to a column (and optionally to an index within it; omit
    ``position`` to append to the end). Authorized via the card's own board — no
    ``board_id`` needed.
    """
    return _client_instance().move_card(card_id, column, position=position)


@mcp.tool()
def claim_card(card_id: int, assignee: str) -> dict[str, Any]:
    """Claim a story in one step: move it to ``in_progress`` **and** set its
    ``assignee`` together. A convenience over calling move_card then update_card
    yourself. Returns the updated card. Authorized via the card's own board — no
    ``board_id`` needed.
    """
    return _client_instance().claim_card(card_id, assignee)


@mcp.tool()
def delete_card(card_id: int) -> dict[str, Any]:
    """Delete a story by id. Authorized via the card's own board."""
    return _client_instance().delete_card(card_id)


@mcp.tool()
def update_epic(
    epic_id: int, name: str | None = None, description: str | None = None
) -> dict[str, Any]:
    """Edit an epic's fields (only the arguments you pass are changed). Authorized
    via the epic's own board — no ``board_id`` needed.
    """
    return _client_instance().update_epic(epic_id, name=name, description=description)


@mcp.tool()
def delete_epic(epic_id: int) -> dict[str, Any]:
    """Delete an epic by id; its child stories are detached (their epic_id is
    cleared), not deleted. Authorized via the epic's own board.
    """
    return _client_instance().delete_epic(epic_id)


# --- card-to-card dependencies (KAN-28 API / KAN-31 tools) -----------------


@mcp.tool()
def add_dependency(card_id: int, blocker_id: int) -> dict[str, Any]:
    """Mark story ``card_id`` as **blocked-by** story ``blocker_id`` (blocker_id
    must finish first). Both must be on the same board (which you own). Returns the
    now-blocked card with its refreshed ``blocked_by`` / ``blocks`` arrays.
    Authorized via the card's own board — no ``board_id`` needed. Rejected (422) on
    a self-link, a duplicate edge, or one that would create a cycle.
    """
    return _client_instance().add_dependency(card_id, blocker_id)


@mcp.tool()
def remove_dependency(card_id: int, blocker_id: int) -> dict[str, Any]:
    """Remove the blocked-by link so story ``card_id`` is no longer blocked-by
    story ``blocker_id``. Returns the card with refreshed dependency arrays.
    Authorized via the card's own board — no ``board_id`` needed. 404 if that link
    doesn't exist.
    """
    return _client_instance().remove_dependency(card_id, blocker_id)


@mcp.tool()
def list_dependencies(card_id: int) -> dict[str, Any]:
    """List a story's dependencies: ``{"card_id": id, "blocked_by": [...],
    "blocks": [...]}``. ``blocked_by`` = ids of stories that block this one (must
    finish first); ``blocks`` = ids it blocks. Reads the card itself (the API
    surfaces these arrays on the card, so ``get_card``/``list_cards`` already
    include them too). Authorized via the card's own board.
    """
    return _client_instance().list_dependencies(card_id)


# --- card work-links (KAN-32 API / KAN-34 tools) ---------------------------


@mcp.tool()
def add_link(card_id: int, label: str, url: str) -> dict[str, Any]:
    """Attach a work-link to story ``card_id`` — a ``label`` (e.g. "PR", "branch",
    "CI") and a ``url`` (the PR URL, branch, CI run, …) — closing the board↔git gap.
    Returns the card with its refreshed ``links`` array. Authorized via the card's
    own board — no ``board_id`` needed. 404 if the card doesn't exist.
    """
    return _client_instance().add_link(card_id, label, url)


@mcp.tool()
def remove_link(card_id: int, link_id: int) -> dict[str, Any]:
    """Detach work-link ``link_id`` from story ``card_id``. Returns the card with its
    refreshed ``links`` array. Authorized via the card's own board — no ``board_id``
    needed. 404 if no such link belongs to the card.
    """
    return _client_instance().remove_link(card_id, link_id)


# --- card notes / comments (KAN-33 API / KAN-34 tools) ---------------------


@mcp.tool()
def add_comment(card_id: int, body: str) -> dict[str, Any]:
    """Post a note (comment) to story ``card_id`` — human/agent-authored context
    like a decision, a handoff, or why something is blocked. The author is the
    acting user (your PAT's owner), never the body. Returns the created comment.
    Authorized via the card's own board — no ``board_id`` needed. 404 if the card
    doesn't exist.
    """
    return _client_instance().add_comment(card_id, body)


@mcp.tool()
def list_comments(card_id: int) -> dict[str, Any]:
    """List a story's notes (comments), oldest-first: ``{"comments": [...]}``. Each
    comment carries id, body, author_id, and created_at. Comments are not inlined on
    card reads (a card can accumulate many), so this is a dedicated read. Authorized
    via the card's own board — no ``board_id`` needed.
    """
    return _client_instance().list_comments(card_id)


def main() -> None:
    """Entry point — run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
