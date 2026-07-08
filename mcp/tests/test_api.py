"""Unit tests for KanbanClient — every method against a mocked transport.

No real server: an ``httpx.MockTransport`` captures each outgoing request so we
can assert method/path/params/body/headers, and returns canned responses so we
can assert the client's return shape and error mapping.
"""
from __future__ import annotations

import httpx
import pytest

from kanban_mcp.api import KanbanApiError, KanbanClient


def make_client(handler, token=None):
    return KanbanClient("http://test", token=token, transport=httpx.MockTransport(handler))


def capture(response):
    """A handler that records the request it saw and returns ``response``."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["headers"] = request.headers
        seen["content"] = request.content
        return response

    return handler, seen


# --- reads -----------------------------------------------------------------


def test_list_cards_passes_filters_and_reads_cursor_header():
    handler, seen = capture(
        httpx.Response(200, json=[{"id": 1}], headers={"X-Next-Cursor": "abc"})
    )
    out = make_client(handler).list_cards(column="todo", limit=2)
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/cards"
    assert seen["params"] == {"column": "todo", "limit": "2"}
    assert out == {"cards": [{"id": 1}], "next_cursor": "abc"}


def test_list_cards_without_more_pages_has_no_cursor():
    handler, _ = capture(httpx.Response(200, json=[]))
    out = make_client(handler).list_cards()
    assert out == {"cards": []}
    assert "next_cursor" not in out


def test_get_card_hits_the_id_path():
    handler, seen = capture(httpx.Response(200, json={"id": 7}))
    out = make_client(handler).get_card(7)
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/cards/7"
    assert out == {"id": 7}


# --- writes ----------------------------------------------------------------


def test_create_card_posts_only_provided_fields():
    import json

    handler, seen = capture(httpx.Response(201, json={"id": 1, "title": "T"}))
    make_client(handler).create_card("T", column="done")
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/cards"
    # None fields (description, story_points, ...) are dropped, not sent as null.
    assert json.loads(seen["content"]) == {"title": "T", "column": "done"}


def test_create_epic_posts_name():
    import json

    handler, seen = capture(httpx.Response(201, json={"id": 1, "name": "E"}))
    make_client(handler).create_epic("E")
    assert seen["path"] == "/api/v1/epics"
    assert json.loads(seen["content"]) == {"name": "E"}


def test_update_card_patches_provided_fields():
    import json

    handler, seen = capture(httpx.Response(200, json={"id": 3}))
    make_client(handler).update_card(3, title="new")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/api/v1/cards/3"
    assert json.loads(seen["content"]) == {"title": "new"}


def test_move_card_posts_to_move_with_column_and_position():
    import json

    handler, seen = capture(httpx.Response(200, json={"id": 5, "column": "done"}))
    make_client(handler).move_card(5, "done", position=0)
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/cards/5/move"
    assert json.loads(seen["content"]) == {"column": "done", "position": 0}


def test_delete_card_sends_delete_and_returns_ack_without_parsing_body():
    handler, seen = capture(httpx.Response(204))  # no JSON body
    out = make_client(handler).delete_card(9)
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/v1/cards/9"
    assert out == {"deleted": 9}


# --- auth + error mapping --------------------------------------------------


def test_token_is_sent_as_bearer_header():
    handler, seen = capture(httpx.Response(201, json={"id": 1}))
    make_client(handler, token="s3cret").create_card("T")
    assert seen["headers"]["authorization"] == "Bearer s3cret"


def test_no_token_means_no_authorization_header():
    handler, seen = capture(httpx.Response(200, json=[]))
    make_client(handler).list_cards()
    assert "authorization" not in seen["headers"]


def test_non_2xx_raises_with_api_detail():
    handler, _ = capture(httpx.Response(401, json={"detail": "missing or invalid API token"}))
    with pytest.raises(KanbanApiError) as excinfo:
        make_client(handler).create_card("T")
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "missing or invalid API token"
    assert "401" in str(excinfo.value)


def test_error_without_json_body_falls_back_to_status():
    handler, _ = capture(httpx.Response(500, text="Internal Server Error"))
    with pytest.raises(KanbanApiError) as excinfo:
        make_client(handler).get_card(1)
    assert excinfo.value.status_code == 500
