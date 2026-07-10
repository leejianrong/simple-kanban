"""Smoke tests for the FastMCP server wiring + board-scoping (V10)."""
from __future__ import annotations

import asyncio
import json

import httpx
from kanban_client import KanbanClient

from kanban_mcp import server
from kanban_mcp.server import mcp

EXPECTED_TOOLS = {
    "list_boards",
    "create_board",
    "list_cards",
    "list_epics",
    "get_card",
    "get_epic",
    "get_board",
    "create_card",
    "create_epic",
    "update_card",
    "move_card",
    "delete_card",
    "update_epic",
    "delete_epic",
    "update_board",
    "delete_board",
    "warmup",
    "claim_card",
    "create_cards",
    "add_dependency",
    "remove_dependency",
    "list_dependencies",
    "add_link",
    "remove_link",
    "add_comment",
    "list_comments",
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


# --- dependency tools (KAN-31) ---------------------------------------------


def _capture_client(monkeypatch, response):
    """Point the server's client at a MockTransport returning ``response`` and
    capture the outgoing method/path/content."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["content"] = request.content
        return response

    client = KanbanClient("http://test", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_client", client)
    monkeypatch.setattr(server, "_default_board_id", None)
    return seen


def test_add_dependency_posts_blocker_id(monkeypatch):
    seen = _capture_client(
        monkeypatch, httpx.Response(201, json={"id": 5, "blocked_by": [2], "blocks": []})
    )
    out = server.add_dependency(5, 2)
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/cards/5/dependencies"
    assert json.loads(seen["content"]) == {"blocker_id": 2}
    assert out == {"id": 5, "blocked_by": [2], "blocks": []}


def test_remove_dependency_deletes_edge_path(monkeypatch):
    seen = _capture_client(
        monkeypatch, httpx.Response(200, json={"id": 5, "blocked_by": [], "blocks": []})
    )
    out = server.remove_dependency(5, 2)
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/v1/cards/5/dependencies/2"
    assert out == {"id": 5, "blocked_by": [], "blocks": []}


def test_list_dependencies_shapes_card_arrays(monkeypatch):
    seen = _capture_client(
        monkeypatch,
        httpx.Response(200, json={"id": 5, "title": "T", "blocked_by": [2, 3], "blocks": [9]}),
    )
    out = server.list_dependencies(5)
    # Reads the card itself — no dedicated endpoint.
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/cards/5"
    assert out == {"card_id": 5, "blocked_by": [2, 3], "blocks": [9]}


# --- work-link + comment tools (KAN-34) ------------------------------------


def test_add_link_posts_label_and_url(monkeypatch):
    seen = _capture_client(
        monkeypatch,
        httpx.Response(201, json={"id": 5, "links": [{"id": 1, "label": "PR", "url": "u"}]}),
    )
    out = server.add_link(5, "PR", "https://example/pr/1")
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/cards/5/links"
    assert json.loads(seen["content"]) == {"label": "PR", "url": "https://example/pr/1"}
    assert out == {"id": 5, "links": [{"id": 1, "label": "PR", "url": "u"}]}


def test_remove_link_deletes_link_path(monkeypatch):
    seen = _capture_client(monkeypatch, httpx.Response(200, json={"id": 5, "links": []}))
    out = server.remove_link(5, 2)
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/v1/cards/5/links/2"
    assert out == {"id": 5, "links": []}


def test_add_comment_posts_body(monkeypatch):
    seen = _capture_client(
        monkeypatch, httpx.Response(201, json={"id": 3, "body": "hi", "author_id": None})
    )
    out = server.add_comment(5, "hi")
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/cards/5/comments"
    assert json.loads(seen["content"]) == {"body": "hi"}
    assert out == {"id": 3, "body": "hi", "author_id": None}


def test_list_comments_reads_and_wraps(monkeypatch):
    seen = _capture_client(
        monkeypatch, httpx.Response(200, json=[{"id": 3, "body": "hi"}])
    )
    out = server.list_comments(5)
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/cards/5/comments"
    assert out == {"comments": [{"id": 3, "body": "hi"}]}
