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


# --- boards (V10) ----------------------------------------------------------


def test_list_boards_hits_boards_and_wraps_result():
    handler, seen = capture(httpx.Response(200, json=[{"id": 1, "name": "A"}]))
    out = make_client(handler).list_boards()
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/boards"
    assert out == {"boards": [{"id": 1, "name": "A"}]}


def test_create_board_posts_name():
    import json

    handler, seen = capture(httpx.Response(201, json={"id": 2, "name": "New"}))
    out = make_client(handler).create_board("New")
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/boards"
    assert json.loads(seen["content"]) == {"name": "New"}
    assert out == {"id": 2, "name": "New"}


def test_update_board_patches_name():
    import json

    handler, seen = capture(httpx.Response(200, json={"id": 2, "name": "Renamed"}))
    out = make_client(handler).update_board(2, name="Renamed")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/api/v1/boards/2"
    assert json.loads(seen["content"]) == {"name": "Renamed"}
    assert out == {"id": 2, "name": "Renamed"}


def test_get_board_hits_the_id_path():
    handler, seen = capture(httpx.Response(200, json={"id": 4, "name": "B"}))
    out = make_client(handler).get_board(4)
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/boards/4"
    assert out == {"id": 4, "name": "B"}


def test_delete_board_sends_delete_and_returns_ack_without_parsing_body():
    handler, seen = capture(httpx.Response(204))  # no JSON body
    out = make_client(handler).delete_board(4)
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/v1/boards/4"
    assert out == {"deleted": 4}


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


def test_list_cards_scopes_by_board_id():
    handler, seen = capture(httpx.Response(200, json=[]))
    make_client(handler).list_cards(board_id=7)
    assert seen["params"] == {"board_id": "7"}


def test_list_epics_scopes_by_board_id_and_wraps_result():
    handler, seen = capture(httpx.Response(200, json=[{"id": 3, "name": "E"}]))
    out = make_client(handler).list_epics(board_id=7)
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/epics"
    assert seen["params"] == {"board_id": "7"}
    assert out == {"epics": [{"id": 3, "name": "E"}]}


def test_list_epics_without_board_sends_no_params():
    handler, seen = capture(httpx.Response(200, json=[]))
    make_client(handler).list_epics()
    assert seen["params"] == {}


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


def test_get_epic_hits_the_id_path():
    handler, seen = capture(httpx.Response(200, json={"id": 3, "name": "E"}))
    out = make_client(handler).get_epic(3)
    assert seen["method"] == "GET"
    assert seen["path"] == "/api/v1/epics/3"
    assert out == {"id": 3, "name": "E"}


# --- writes ----------------------------------------------------------------


def test_create_card_posts_only_provided_fields():
    import json

    handler, seen = capture(httpx.Response(201, json={"id": 1, "title": "T"}))
    make_client(handler).create_card("T", column="done")
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/cards"
    # None fields (description, story_points, ...) are dropped, not sent as null.
    assert json.loads(seen["content"]) == {"title": "T", "column": "done"}


def test_create_card_includes_board_id_when_given():
    import json

    handler, seen = capture(httpx.Response(201, json={"id": 1}))
    make_client(handler).create_card("T", board_id=7)
    assert json.loads(seen["content"]) == {"board_id": 7, "title": "T"}


def test_create_epic_posts_name():
    import json

    handler, seen = capture(httpx.Response(201, json={"id": 1, "name": "E"}))
    make_client(handler).create_epic("E")
    assert seen["path"] == "/api/v1/epics"
    assert json.loads(seen["content"]) == {"name": "E"}


def test_create_epic_includes_board_id_when_given():
    import json

    handler, seen = capture(httpx.Response(201, json={"id": 1, "name": "E"}))
    make_client(handler).create_epic("E", board_id=7)
    assert json.loads(seen["content"]) == {"board_id": 7, "name": "E"}


def test_update_card_patches_provided_fields():
    import json

    handler, seen = capture(httpx.Response(200, json={"id": 3}))
    make_client(handler).update_card(3, title="new")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/api/v1/cards/3"
    assert json.loads(seen["content"]) == {"title": "new"}


def test_update_epic_patches_only_provided_fields():
    import json

    handler, seen = capture(httpx.Response(200, json={"id": 3, "name": "E"}))
    make_client(handler).update_epic(3, name="E")
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/api/v1/epics/3"
    # None fields (description) are dropped, not sent as null.
    assert json.loads(seen["content"]) == {"name": "E"}


def test_delete_epic_sends_delete_and_returns_ack_without_parsing_body():
    handler, seen = capture(httpx.Response(204))  # no JSON body
    out = make_client(handler).delete_epic(8)
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/v1/epics/8"
    assert out == {"deleted": 8}


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


def test_401_raises_with_friendly_hint_and_raw_detail():
    handler, _ = capture(httpx.Response(401, json={"detail": "authentication required"}))
    with pytest.raises(KanbanApiError) as excinfo:
        make_client(handler).create_card("T")
    assert excinfo.value.status_code == 401
    # The raw server detail is preserved ...
    assert excinfo.value.detail == "authentication required"
    # ... and the agent-facing message frames it as a token problem (V10).
    assert "401" in str(excinfo.value)
    assert "KANBAN_TOKEN" in str(excinfo.value)


def test_403_raises_with_wrong_board_hint():
    handler, _ = capture(
        httpx.Response(403, json={"detail": "you do not have access to this board"})
    )
    with pytest.raises(KanbanApiError) as excinfo:
        make_client(handler).create_card("T", board_id=99)
    assert excinfo.value.status_code == 403
    assert "list_boards" in str(excinfo.value)


def test_error_without_json_body_falls_back_to_status():
    handler, _ = capture(httpx.Response(500, text="Internal Server Error"))
    with pytest.raises(KanbanApiError) as excinfo:
        make_client(handler).get_card(1)
    assert excinfo.value.status_code == 500
