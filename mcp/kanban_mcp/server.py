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
Priority = Literal["none", "low", "medium", "high", "urgent"]

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


def _require_board(board_id: int | None) -> int:
    """Like :func:`_board`, but the target board id is **required** (the path-scoped
    board tools have no API-side fallback). Raises when neither a per-call
    ``board_id`` nor ``KANBAN_BOARD_ID`` is set."""
    resolved = _board(board_id)
    if resolved is None:
        raise ValueError("board_id is required (set KANBAN_BOARD_ID or pass board_id)")
    return resolved


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
    priority: Priority | None = None,
    label: int | None = None,
    due_before: str | None = None,
    overdue: bool | None = None,
    needs_human: bool | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List/query stories. ``board_id`` targets one board (defaults to
    KANBAN_BOARD_ID; omit both to span all your boards). Other filters (AND-ed):
    column, epic_id, updated_since (an ISO-8601 timestamp — stories changed
    at/after it), priority, label (a label id), due_before (an ISO-8601 timestamp —
    stories due strictly before it), overdue (true → past-due and not done), and
    needs_human (true → cards flagged for a human via needs_human; false → the rest).
    Paginate with limit; if more results remain the response includes
    ``next_cursor`` to pass back as ``cursor``.
    """
    return _client_instance().list_cards(
        board_id=_board(board_id),
        column=column,
        epic_id=epic_id,
        updated_since=updated_since,
        priority=priority,
        label=label,
        due_before=due_before,
        overdue=overdue,
        needs_human=needs_human,
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
    priority: Priority | None = None,
    due_date: str | None = None,
    label_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Create a story. Only ``title`` is required; it lands at the end of its
    column (default ``todo``). ``board_id`` targets one board (defaults to
    KANBAN_BOARD_ID; omit both to use your earliest board). ``story_points`` must
    be one of 1/2/3/5/8/13. ``epic_id`` links it to an existing epic on the same
    board. ``priority`` is one of none/low/medium/high/urgent (default none);
    ``due_date`` is an ISO-8601 timestamp; ``label_ids`` attaches board labels
    (each must belong to the card's board — see create_label/list_labels).
    """
    return _client_instance().create_card(
        title,
        board_id=_board(board_id),
        description=description,
        column=column,
        story_points=story_points,
        assignee=assignee,
        epic_id=epic_id,
        priority=priority,
        due_date=due_date,
        label_ids=label_ids,
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
    priority: Priority | None = None,
    due_date: str | None = None,
    label_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Edit a story's fields (only the arguments you pass are changed). Use
    move_card to change column/position, not this. ``priority`` re-ranks;
    ``due_date`` is an ISO-8601 timestamp; ``label_ids`` **replaces** the card's
    label set (``[]`` clears it — each id must belong to the card's board).
    Authorized via the card's own board — no ``board_id`` needed.
    """
    return _client_instance().update_card(
        card_id,
        title=title,
        description=description,
        story_points=story_points,
        assignee=assignee,
        epic_id=epic_id,
        priority=priority,
        due_date=due_date,
        label_ids=label_ids,
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


# --- board labels (M5 V11 API / KAN-244 tools) ----------------------------


@mcp.tool()
def list_labels(board_id: int | None = None) -> dict[str, Any]:
    """List a board's labels (id, name, color). ``board_id`` targets one board
    (defaults to KANBAN_BOARD_ID). Use the returned ids in ``label_ids`` on
    create_card/update_card, or as the ``label`` filter on list_cards."""
    resolved = _board(board_id)
    if resolved is None:
        raise ValueError("board_id is required (set KANBAN_BOARD_ID or pass board_id)")
    return _client_instance().list_labels(resolved)


@mcp.tool()
def create_label(name: str, color: str, board_id: int | None = None) -> dict[str, Any]:
    """Create a board-scoped label — a ``name`` and a ``color`` (e.g. a hex like
    ``#0ea5e9``). ``board_id`` targets one board (defaults to KANBAN_BOARD_ID).
    Returns the created label; attach it to cards via ``label_ids``."""
    resolved = _board(board_id)
    if resolved is None:
        raise ValueError("board_id is required (set KANBAN_BOARD_ID or pass board_id)")
    return _client_instance().create_label(resolved, name, color)


@mcp.tool()
def delete_label(label_id: int) -> dict[str, Any]:
    """Delete a label by id; it detaches from every card that carried it.
    Authorized via the label's own board — no ``board_id`` needed."""
    return _client_instance().delete_label(label_id)


# --- dispatch + fleet-safe claim (M5 V12 API / KAN-245 tools) --------------


@mcp.tool()
def dispatch(
    board_id: int | None = None,
    assignee: str | None = None,
    label: int | None = None,
    priority: Priority | None = None,
) -> dict[str, Any]:
    """Atomically claim the next ready-to-work story on a board and start it — the
    agent's "give me something to do" call. The API picks the next unblocked
    ``todo`` story (highest ``priority`` first, then board order), sets its
    ``assignee`` (defaults to you), and moves it to ``in_progress`` in one
    ``FOR UPDATE SKIP LOCKED`` transaction, so many agents can dispatch at once and
    never grab the same card. ``board_id`` targets one board (defaults to
    KANBAN_BOARD_ID). ``label`` / ``priority`` (a *minimum*) narrow the selection.
    Returns ``{"card": <story>}``, or ``{"card": null}`` when nothing is ready.
    """
    return _client_instance().dispatch(
        _require_board(board_id), assignee=assignee, label=label, priority=priority
    )


@mcp.tool(name="next")
def next_ready(
    board_id: int | None = None,
    label: int | None = None,
    priority: Priority | None = None,
) -> dict[str, Any]:
    """Peek at the next ready-to-work story on a board **without** claiming it — the
    same selection as ``dispatch`` (next unblocked ``todo`` story, highest
    ``priority`` first) but read-only, so you can see what's up next before pulling
    it. ``board_id`` targets one board (defaults to KANBAN_BOARD_ID). ``label`` /
    ``priority`` (a *minimum*) narrow the selection. Returns ``{"card": <story>}``,
    or ``{"card": null}`` when nothing is ready.
    """
    return _client_instance().next_ready(
        _require_board(board_id), label=label, priority=priority
    )


# --- needs-human handoff (M5 V13 API / KAN-246 tools) ----------------------


@mcp.tool()
def needs_human(card_id: int, attention_note: str | None = None) -> dict[str, Any]:
    """Flag story ``card_id`` as needing a human — use this when you hit something
    only a person can settle (a decision, missing access, a stuck PR). Pass an
    optional ``attention_note`` describing the ask. Returns the updated card
    (``needs_human=true``); it then shows on the board with a needs-human badge and
    is findable via ``list_cards(needs_human=true)``. A human clears it with
    ``resolve`` and typically replies via a comment — poll the card's flag +
    comments to see the resolution. Authorized via the card's own board.
    """
    return _client_instance().flag_needs_human(card_id, attention_note=attention_note)


@mcp.tool()
def resolve(card_id: int) -> dict[str, Any]:
    """Clear the needs-human flag on story ``card_id`` (``needs_human=false``, the
    attention note is cleared). The human-facing counterpart to ``needs_human``;
    typically you also add a comment explaining the resolution. Returns the updated
    card. Authorized via the card's own board — no ``board_id`` needed.
    """
    return _client_instance().resolve_card(card_id)


# --- fleet reporting / metrics (M5 V17 API / KAN-250 tools) ----------------


@mcp.tool()
def metrics(
    board_id: int | None = None,
    since: str | None = None,
    window: str | None = None,
) -> dict[str, Any]:
    """Report derived flow metrics for a board — throughput (cards done in the
    period), cycle time (first in_progress → done: avg/median/p90 seconds), aging
    WIP (how long each in-flight card has sat in progress), and a per-assignee
    breakdown (completed + open WIP per agent). All computed from the activity feed
    + card timestamps; nothing is written. ``board_id`` targets one board (defaults
    to KANBAN_BOARD_ID). Bound the period with ``since`` (an ISO-8601 timestamp) or
    ``window`` (``7d`` / ``24h`` / ``30m``); omit both for all time. Authorized via
    the board (you must be able to read it).
    """
    return _client_instance().board_metrics(
        _require_board(board_id), since=since, window=window
    )


def main() -> None:
    """Entry point — run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
