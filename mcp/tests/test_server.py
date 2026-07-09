"""Smoke tests for the FastMCP server wiring + board-scoping (V10)."""
from __future__ import annotations

import asyncio
import json

import httpx

from kanban_mcp import server
from kanban_mcp.api import KanbanClient
from kanban_mcp.server import mcp

EXPECTED_TOOLS = {
    "list_boards",
    "create_board",
    "list_cards",
    "list_epics",
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


# --- board-scoping default resolution (V10) --------------------------------


def _stub_client(monkeypatch, default_board_id):
    """Point the server's lazily-built client at a MockTransport and set the
    KANBAN_BOARD_ID default, capturing the outgoing request."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["content"] = request.content
        return httpx.Response(201, json={"id": 1})

    client = KanbanClient("http://test", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_client", client)
    monkeypatch.setattr(server, "_default_board_id", default_board_id)
    return seen


def test_create_card_falls_back_to_default_board(monkeypatch):
    seen = _stub_client(monkeypatch, default_board_id=7)
    server.create_card("T")
    assert json.loads(seen["content"]) == {"board_id": 7, "title": "T"}


def test_per_call_board_id_overrides_the_default(monkeypatch):
    seen = _stub_client(monkeypatch, default_board_id=7)
    server.create_card("T", board_id=3)
    assert json.loads(seen["content"]) == {"board_id": 3, "title": "T"}


def test_no_board_id_and_no_default_sends_none(monkeypatch):
    seen = _stub_client(monkeypatch, default_board_id=None)
    server.list_cards()
    assert seen["params"] == {}
