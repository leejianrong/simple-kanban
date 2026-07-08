"""MCP server exposing the Simple Kanban API as agent tools (stdio transport).

Each tool is a thin wrapper over one ``/api/v1`` endpoint via ``KanbanClient``.
Type hints + docstrings here become the tool schema + description the agent sees
(FastMCP). Reads need no token; writes require ``KANBAN_TOKEN`` only when the
target server has ``API_TOKENS`` set (ADR 0010) — otherwise a write returns 401
and the tool surfaces that message.

Run with ``python -m kanban_mcp`` (or the ``kanban-mcp`` script); Claude Code
launches it over stdio per the .mcp.json snippet in the README.
"""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .api import KanbanClient
from .config import load_config

Column = Literal["todo", "in_progress", "done"]

mcp = FastMCP("kanban")

_client: KanbanClient | None = None


def _client_instance() -> KanbanClient:
    """Lazily build the API client from the environment on first tool use."""
    global _client
    if _client is None:
        config = load_config()
        _client = KanbanClient(config.api_url, config.token)
    return _client


@mcp.tool()
def list_cards(
    column: Column | None = None,
    epic_id: int | None = None,
    updated_since: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List/query stories on the board.

    Optional filters (combined with AND): column, epic_id, and updated_since (an
    ISO-8601 timestamp — stories changed at/after it). Paginate with limit; if
    more results remain the response includes ``next_cursor`` to pass back as
    ``cursor``. With no arguments, returns every story.
    """
    return _client_instance().list_cards(
        column=column,
        epic_id=epic_id,
        updated_since=updated_since,
        limit=limit,
        cursor=cursor,
    )


@mcp.tool()
def get_card(card_id: int) -> dict[str, Any]:
    """Fetch a single story by its numeric id."""
    return _client_instance().get_card(card_id)


@mcp.tool()
def create_card(
    title: str,
    description: str | None = None,
    column: Column | None = None,
    story_points: int | None = None,
    assignee: str | None = None,
    epic_id: int | None = None,
) -> dict[str, Any]:
    """Create a story. Only ``title`` is required; it lands at the end of its
    column (default ``todo``). ``story_points`` must be one of 1/2/3/5/8/13.
    ``epic_id`` links it to an existing epic. Requires a write token if the
    server has auth enabled.
    """
    return _client_instance().create_card(
        title,
        description=description,
        column=column,
        story_points=story_points,
        assignee=assignee,
        epic_id=epic_id,
    )


@mcp.tool()
def create_epic(name: str, description: str | None = None) -> dict[str, Any]:
    """Create an epic (a board-less grouping stories can link to via epic_id).
    Requires a write token if the server has auth enabled.
    """
    return _client_instance().create_epic(name, description=description)


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
    move_card to change column/position, not this. Requires a write token if the
    server has auth enabled.
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
    ``position`` to append to the end). Requires a write token if the server has
    auth enabled.
    """
    return _client_instance().move_card(card_id, column, position=position)


@mcp.tool()
def delete_card(card_id: int) -> dict[str, Any]:
    """Delete a story by id. Requires a write token if the server has auth enabled."""
    return _client_instance().delete_card(card_id)


def main() -> None:
    """Entry point — run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
