"""API tests for the card query API (Milestone 2 V3, P4).

Covers the optional filters (column / epic_id / updated_since), keyset
pagination via limit + the X-Next-Cursor header, combined filters, empty
results, bad inputs, and back-compat (no params = the full list). Per the suite
convention, any app-module imports go inside test bodies, not at module top.
"""
from __future__ import annotations

CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"
NEXT_CURSOR = "X-Next-Cursor"


def _create(client, **fields):
    return client.post(CARDS, json={"title": "T", **fields}).json()


# --- back-compat -----------------------------------------------------------


def test_no_params_returns_full_list(client):
    _create(client, title="A")
    _create(client, title="B", column="done")
    r = client.get(CARDS)
    assert r.status_code == 200
    assert {c["title"] for c in r.json()} == {"A", "B"}
    # An unpaginated response carries no cursor.
    assert NEXT_CURSOR not in r.headers


# --- filters ---------------------------------------------------------------


def test_filter_by_column(client):
    _create(client, title="todo1", column="todo")
    _create(client, title="done1", column="done")
    _create(client, title="todo2", column="todo")
    r = client.get(CARDS, params={"column": "todo"})
    assert r.status_code == 200
    assert {c["title"] for c in r.json()} == {"todo1", "todo2"}


def test_filter_by_epic_id(client):
    epic = client.post(EPICS, json={"name": "E1"}).json()
    other = client.post(EPICS, json={"name": "E2"}).json()
    _create(client, title="in", epic_id=epic["id"])
    _create(client, title="other", epic_id=other["id"])
    _create(client, title="unassigned")
    r = client.get(CARDS, params={"epic_id": epic["id"]})
    assert [c["title"] for c in r.json()] == ["in"]


def test_filter_by_updated_since_is_inclusive(client):
    a = _create(client, title="A")
    # updated_since equal to A's own updated_at includes A (inclusive boundary).
    r = client.get(CARDS, params={"updated_since": a["updated_at"]})
    assert a["id"] in {c["id"] for c in r.json()}


def test_updated_since_excludes_older_rows(client):
    a = _create(client, title="old")
    # Touch B so it updates strictly after A.
    b = _create(client, title="new")
    b = client.patch(f"{CARDS}/{b['id']}", json={"title": "new2"}).json()
    r = client.get(CARDS, params={"updated_since": b["updated_at"]})
    ids = {c["id"] for c in r.json()}
    assert b["id"] in ids
    assert a["id"] not in ids


def test_filters_combine_with_and(client):
    epic = client.post(EPICS, json={"name": "E"}).json()
    _create(client, title="match", column="todo", epic_id=epic["id"])
    _create(client, title="wrong-col", column="done", epic_id=epic["id"])
    _create(client, title="wrong-epic", column="todo")
    r = client.get(CARDS, params={"column": "todo", "epic_id": epic["id"]})
    assert [c["title"] for c in r.json()] == ["match"]


def test_empty_result_is_valid_and_carries_no_cursor(client):
    _create(client, title="only-todo", column="todo")
    r = client.get(CARDS, params={"column": "done", "limit": 5})
    assert r.status_code == 200
    assert r.json() == []
    assert NEXT_CURSOR not in r.headers


# --- pagination ------------------------------------------------------------


def test_limit_caps_page_and_emits_cursor(client):
    for i in range(3):
        _create(client, title=f"c{i}")
    r = client.get(CARDS, params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert NEXT_CURSOR in r.headers


def test_paging_walks_disjoint_gapless_pages(client):
    created = [_create(client, title=f"c{i}") for i in range(5)]
    all_ids = {c["id"] for c in created}

    seen: list[int] = []
    params = {"limit": 2}
    for _ in range(10):  # generous cap to avoid an infinite loop on a bug
        r = client.get(CARDS, params=params)
        assert r.status_code == 200
        page = r.json()
        seen.extend(c["id"] for c in page)
        cursor = r.headers.get(NEXT_CURSOR)
        if cursor is None:
            break
        params = {"limit": 2, "cursor": cursor}

    # Disjoint (no repeats), gap-free (covers everything), and cursor-ordered.
    assert len(seen) == len(set(seen))
    assert set(seen) == all_ids


def test_last_page_omits_cursor(client):
    for i in range(4):
        _create(client, title=f"c{i}")
    # A page smaller than the limit is the last one — no cursor.
    r = client.get(CARDS, params={"limit": 10})
    assert len(r.json()) == 4
    assert NEXT_CURSOR not in r.headers


def test_pagination_is_ordered_by_updated_at_then_id(client):
    created = [_create(client, title=f"c{i}") for i in range(4)]
    r = client.get(CARDS, params={"limit": 4})
    returned_ids = [c["id"] for c in r.json()]
    # (updated_at, id) ascending == insertion order here (id breaks any tie).
    assert returned_ids == [c["id"] for c in created]


# --- bad inputs ------------------------------------------------------------


def test_unknown_column_rejected(client):
    assert client.get(CARDS, params={"column": "backlog"}).status_code == 422


def test_malformed_cursor_rejected(client):
    assert client.get(CARDS, params={"cursor": "not-a-valid-cursor!!"}).status_code == 422


def test_out_of_range_limit_rejected(client):
    assert client.get(CARDS, params={"limit": 0}).status_code == 422
    assert client.get(CARDS, params={"limit": 201}).status_code == 422
