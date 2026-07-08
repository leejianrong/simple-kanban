"""Smoke tests for the FastMCP server wiring."""
from __future__ import annotations

import asyncio

from kanban_mcp.server import mcp

EXPECTED_TOOLS = {
    "list_cards",
    "get_card",
    "create_card",
    "create_epic",
    "update_card",
    "move_card",
    "delete_card",
}


def _tools():
    return asyncio.run(mcp.list_tools())


def test_server_advertises_exactly_the_expected_tools():
    assert {tool.name for tool in _tools()} == EXPECTED_TOOLS


def test_every_tool_has_a_description_and_schema():
    for tool in _tools():
        assert tool.description, f"{tool.name} is missing a description"
        assert tool.inputSchema, f"{tool.name} is missing an input schema"


def test_create_card_schema_marks_title_required():
    create_card = next(t for t in _tools() if t.name == "create_card")
    assert create_card.inputSchema["required"] == ["title"]
