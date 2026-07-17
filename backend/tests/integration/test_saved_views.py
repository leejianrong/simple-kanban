"""API tests for the query grammar + saved views (M5 V14, KAN-247).

Covers the new ``assignee`` filter and the ``sort`` grammar (priority-rank, due
date, position; ascending/descending; combined; bad inputs), plus the saved-view
CRUD and its central guarantee — a stored view's ``query``, replayed as ``GET
/cards`` params, reproduces its result set. Board-scoped + auth-gated (non-member
403, cross-board 404). Per the suite convention, any app-module imports go inside
test bodies, not at module top (the PR #17 trap)."""
from __future__ import annotations

import pytest


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so these tests run as the
    board-owning session user (shadows conftest's unauthenticated ``client``).
    Claim-on-login makes this user own the reset fixture's default board (id=1)."""
    return logged_in_client


CARDS = "/api/v1/cards"


def _create(client, **fields):
    return client.post(CARDS, json={"title": "T", **fields}).json()


def _views(board_id: int) -> str:
    return f"/api/v1/boards/{board_id}/views"


# --- assignee filter --------------------------------------------------------


def test_filter_by_assignee(client):
    _create(client, title="mine", assignee="agent-7")
    _create(client, title="theirs", assignee="agent-9")
    _create(client, title="none")
    r = client.get(CARDS, params={"assignee": "agent-7"})
    assert r.status_code == 200
    assert [c["title"] for c in r.json()] == ["mine"]


def test_assignee_combines_with_other_filters(client):
    _create(client, title="match", assignee="a", priority="high")
    _create(client, title="wrong-pri", assignee="a", priority="low")
    _create(client, title="wrong-assignee", assignee="b", priority="high")
    r = client.get(CARDS, params={"assignee": "a", "priority": "high"})
    assert [c["title"] for c in r.json()] == ["match"]


# --- sort grammar -----------------------------------------------------------


def test_sort_by_priority_descending_is_urgent_first(client):
    _create(client, title="none", priority="none")
    _create(client, title="urgent", priority="urgent")
    _create(client, title="low", priority="low")
    _create(client, title="high", priority="high")
    r = client.get(CARDS, params={"sort": "-priority"})
    assert [c["title"] for c in r.json()] == ["urgent", "high", "low", "none"]


def test_sort_by_priority_ascending_is_none_first(client):
    _create(client, title="urgent", priority="urgent")
    _create(client, title="none", priority="none")
    _create(client, title="medium", priority="medium")
    r = client.get(CARDS, params={"sort": "priority"})
    assert [c["title"] for c in r.json()] == ["none", "medium", "urgent"]


def test_sort_by_due_date_nulls_sink(client):
    _create(client, title="soon", due_date="2026-01-01T00:00:00Z")
    _create(client, title="later", due_date="2026-12-01T00:00:00Z")
    _create(client, title="no-due")
    # Ascending: soonest first, the null due-date card last (NULLS LAST).
    r = client.get(CARDS, params={"sort": "due_date"})
    assert [c["title"] for c in r.json()] == ["soon", "later", "no-due"]
    # Descending: latest first, null still last (NULLS LAST both ways).
    r = client.get(CARDS, params={"sort": "-due_date"})
    assert [c["title"] for c in r.json()] == ["later", "soon", "no-due"]


def test_sort_combined_keys(client):
    # priority desc, then position asc within a priority.
    a = _create(client, title="high-a", priority="high")
    b = _create(client, title="high-b", priority="high")
    _create(client, title="low", priority="low")
    # a and b are both 'high' and share the todo column, so position breaks the tie
    # (creation order == append order).
    r = client.get(CARDS, params={"sort": "-priority,position"})
    titles = [c["title"] for c in r.json()]
    assert titles[0] in {"high-a", "high-b"}
    assert titles[-1] == "low"
    assert titles.index("high-a") < titles.index("high-b")
    assert a["position"] < b["position"]


def test_unknown_sort_field_is_422(client):
    assert client.get(CARDS, params={"sort": "bogus"}).status_code == 422


def test_sort_with_cursor_is_422(client):
    _create(client, title="c")
    assert client.get(
        CARDS, params={"sort": "priority", "cursor": "anything"}
    ).status_code == 422


def test_sort_emits_no_cursor_header(client):
    for i in range(3):
        _create(client, title=f"c{i}")
    r = client.get(CARDS, params={"sort": "priority", "limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2  # limit still caps a top-N
    assert "X-Next-Cursor" not in r.headers


# --- saved-view CRUD --------------------------------------------------------


def test_create_list_get_delete_view(client):
    created = client.post(
        _views(1), json={"name": "needs me", "query": {"priority": "high"}}
    )
    assert created.status_code == 201
    view = created.json()
    assert view["board_id"] == 1
    assert view["name"] == "needs me"
    assert view["query"] == {"priority": "high"}

    listed = client.get(_views(1))
    assert listed.status_code == 200
    assert [v["id"] for v in listed.json()] == [view["id"]]

    got = client.get(f"{_views(1)}/{view['id']}")
    assert got.status_code == 200
    assert got.json()["query"] == {"priority": "high"}

    deleted = client.delete(f"{_views(1)}/{view['id']}")
    assert deleted.status_code == 204
    assert client.get(_views(1)).json() == []


def test_create_view_defaults_to_empty_query(client):
    view = client.post(_views(1), json={"name": "all"}).json()
    assert view["query"] == {}


def test_create_view_rejects_bad_query(client):
    r = client.post(_views(1), json={"name": "bad", "query": {"sort": "nope"}})
    assert r.status_code == 422


def test_create_view_rejects_blank_name(client):
    assert client.post(_views(1), json={"name": "  "}).status_code == 422


# --- the reproduction guarantee ---------------------------------------------


def test_saved_view_query_reproduces_its_result_set(client):
    _create(client, title="hi-1", priority="high", assignee="me")
    _create(client, title="hi-2", priority="high", assignee="you")
    _create(client, title="lo", priority="low", assignee="me")

    # Save a view "high + mine, urgent-first".
    query = {"priority": "high", "assignee": "me", "sort": "-priority"}
    view = client.post(_views(1), json={"name": "hi-mine", "query": query}).json()

    # Replaying the stored query as GET /cards params reproduces the set...
    replayed = client.get(CARDS, params=view["query"])
    assert replayed.status_code == 200
    replayed_titles = [c["title"] for c in replayed.json()]
    assert replayed_titles == ["hi-1"]

    # ...and it equals a direct query with the same params (the grammar is one).
    direct = client.get(CARDS, params=query)
    assert [c["title"] for c in direct.json()] == replayed_titles


# --- board-scoping + authz --------------------------------------------------


def test_views_are_board_scoped(client):
    other = client.post("/api/v1/boards", json={"name": "Other"}).json()
    v1 = client.post(_views(1), json={"name": "on-1"}).json()
    client.post(_views(other["id"]), json={"name": "on-2"})
    # The default board's list only shows its own view.
    assert [v["name"] for v in client.get(_views(1)).json()] == ["on-1"]
    assert [v["name"] for v in client.get(_views(other["id"])).json()] == ["on-2"]
    # v1 addressed under the wrong board 404s (cross-board id not reachable).
    assert client.get(f"{_views(other['id'])}/{v1['id']}").status_code == 404
    assert client.delete(f"{_views(other['id'])}/{v1['id']}").status_code == 404


def test_get_missing_view_is_404(client):
    assert client.get(f"{_views(1)}/9999").status_code == 404


def test_non_member_cannot_touch_a_board_view(client, login_as):
    # `client` (FAKE_EMAIL) owns board 1 and creates a view on it.
    view = client.post(_views(1), json={"name": "private"}).json()
    # A second, unrelated user has no access to board 1.
    stranger = login_as("stranger@example.com", "gh-stranger")
    assert stranger.get(_views(1)).status_code == 403
    assert stranger.post(_views(1), json={"name": "nope"}).status_code == 403
    assert stranger.get(f"{_views(1)}/{view['id']}").status_code == 403
    assert stranger.delete(f"{_views(1)}/{view['id']}").status_code == 403


def test_views_on_unknown_board_is_404(client):
    assert client.get(_views(9999)).status_code == 404
    assert client.post(_views(9999), json={"name": "x"}).status_code == 404
