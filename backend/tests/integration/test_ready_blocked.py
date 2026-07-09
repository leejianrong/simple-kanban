"""API tests for the ready/blocked signal on the card query API (KAN-29).

Covers the derived ``blocked`` field on reads (list + detail), the
``blocked=true|false`` list filter, that a blocker in the ``done`` column no
longer counts (ready again), that the filter AND-s with the other filters, and
that it composes with keyset pagination. Uses only the HTTP client — per the
suite convention, any app-module imports go inside test bodies, not module top.
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"
NEXT_CURSOR = "X-Next-Cursor"


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so these tests run as the
    board-owning session user (claim-on-login gives them the default board)."""
    return logged_in_client


def _card(client, title="T", **fields):
    r = client.post(CARDS, json={"title": title, **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _add_dep(client, blocked_id, blocker_id):
    """Record that ``blocked_id`` is blocked-by ``blocker_id``."""
    r = client.post(f"{CARDS}/{blocked_id}/dependencies", json={"blocker_id": blocker_id})
    assert r.status_code == 201, r.text
    return r.json()


# --- the blocked field -------------------------------------------------------


def test_blocked_false_when_no_dependencies(client):
    card = _card(client, "lonely")
    assert card["blocked"] is False
    assert client.get(f"{CARDS}/{card['id']}").json()["blocked"] is False


def test_blocked_true_when_blocker_not_done(client):
    blocker = _card(client, "blocker", column="todo")
    blocked = _card(client, "blocked")
    body = _add_dep(client, blocked["id"], blocker["id"])
    # The POST /dependencies response reflects it immediately.
    assert body["blocked"] is True
    # And it shows up on both detail and list reads.
    assert client.get(f"{CARDS}/{blocked['id']}").json()["blocked"] is True
    listed = {c["id"]: c for c in client.get(CARDS).json()}
    assert listed[blocked["id"]]["blocked"] is True
    # The blocker itself is not blocked.
    assert listed[blocker["id"]]["blocked"] is False


def test_blocked_false_when_only_blocker_is_done(client):
    blocker = _card(client, "blocker", column="done")
    blocked = _card(client, "blocked")
    body = _add_dep(client, blocked["id"], blocker["id"])
    # A done blocker does not count — the card is ready even with a blocked_by edge.
    assert body["blocked"] is False
    assert body["blocked_by"] == [blocker["id"]]


def test_moving_blocker_to_done_makes_card_ready(client):
    blocker = _card(client, "blocker", column="todo")
    blocked = _card(client, "blocked")
    _add_dep(client, blocked["id"], blocker["id"])
    assert client.get(f"{CARDS}/{blocked['id']}").json()["blocked"] is True

    # Complete the blocker.
    r = client.post(f"{CARDS}/{blocker['id']}/move", json={"column": "done"})
    assert r.status_code == 200, r.text
    assert client.get(f"{CARDS}/{blocked['id']}").json()["blocked"] is False


def test_blocked_true_if_any_blocker_not_done(client):
    done_blocker = _card(client, "done-blocker", column="done")
    open_blocker = _card(client, "open-blocker", column="in_progress")
    blocked = _card(client, "blocked")
    _add_dep(client, blocked["id"], done_blocker["id"])
    _add_dep(client, blocked["id"], open_blocker["id"])
    # One done + one open blocker → still blocked (>=1 active blocker).
    assert client.get(f"{CARDS}/{blocked['id']}").json()["blocked"] is True


# --- the blocked filter ------------------------------------------------------


def test_filter_blocked_true(client):
    blocker = _card(client, "blocker", column="todo")
    blocked = _card(client, "blocked")
    _card(client, "free")
    _add_dep(client, blocked["id"], blocker["id"])
    r = client.get(CARDS, params={"blocked": "true"})
    assert r.status_code == 200
    assert [c["title"] for c in r.json()] == ["blocked"]


def test_filter_blocked_false_returns_ready_cards(client):
    blocker = _card(client, "blocker", column="todo")
    blocked = _card(client, "blocked")
    _card(client, "free")
    done_blocker = _card(client, "done-blocker", column="done")
    ready_via_done = _card(client, "ready-via-done")
    _add_dep(client, blocked["id"], blocker["id"])
    _add_dep(client, ready_via_done["id"], done_blocker["id"])

    r = client.get(CARDS, params={"blocked": "false"})
    assert r.status_code == 200
    titles = {c["title"] for c in r.json()}
    # Ready = no active blocker: the free card, the card whose only blocker is
    # done, plus the blocker cards themselves (nothing blocks them). NOT "blocked".
    assert "blocked" not in titles
    assert {"free", "blocker", "done-blocker", "ready-via-done"} <= titles


def test_filter_blocked_ands_with_column(client):
    blocker = _card(client, "blocker", column="todo")
    b_todo = _card(client, "blocked-todo", column="todo")
    b_done = _card(client, "blocked-done", column="done")
    _add_dep(client, b_todo["id"], blocker["id"])
    _add_dep(client, b_done["id"], blocker["id"])
    # blocked=true AND column=todo → only the blocked card in the todo column.
    r = client.get(CARDS, params={"blocked": "true", "column": "todo"})
    assert [c["title"] for c in r.json()] == ["blocked-todo"]


def test_filter_composes_with_pagination(client):
    blocker = _card(client, "blocker", column="todo")
    blocked_ids = set()
    for i in range(5):
        b = _card(client, f"blocked-{i}")
        _add_dep(client, b["id"], blocker["id"])
        blocked_ids.add(b["id"])
    # Some unblocked noise that must never appear in a blocked=true page.
    for i in range(3):
        _card(client, f"free-{i}")

    seen: list[int] = []
    params = {"blocked": "true", "limit": 2}
    for _ in range(10):  # generous cap against an infinite loop on a bug
        r = client.get(CARDS, params=params)
        assert r.status_code == 200
        page = r.json()
        assert all(c["blocked"] is True for c in page)
        seen.extend(c["id"] for c in page)
        cursor = r.headers.get(NEXT_CURSOR)
        if cursor is None:
            break
        params = {"blocked": "true", "limit": 2, "cursor": cursor}

    # Disjoint, gap-free over exactly the blocked cards.
    assert len(seen) == len(set(seen))
    assert set(seen) == blocked_ids
