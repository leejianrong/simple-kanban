"""API tests for card fields — priority, due date, labels (M5 V11, KAN-244).

Covers: setting/reading ``priority`` + ``due_date`` + ``labels`` on create and
update; the priority CHECK (bad value → 422 at the API, and the DB constraint
itself); board-scoped labels (attaching another board's label → 422); the list
filters (priority / label / due_before / overdue); label CRUD + authorization; and
the cascade that detaches a label from its cards when the label is deleted.

Per the suite convention, any app-module imports go inside test bodies, not at
module top (the PR #17 trap).
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
BOARDS = "/api/v1/boards"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so these tests run as the
    board-owning session user (claim-on-login gives them the default board)."""
    return logged_in_client


def _card(client, title="T", **fields):
    r = client.post(CARDS, json={"title": title, **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _label(client, board_id, name="bug", color="#ef4444"):
    r = client.post(f"{BOARDS}/{board_id}/labels", json={"name": name, "color": color})
    assert r.status_code == 201, r.text
    return r.json()


def _default_board(client) -> int:
    return client.get(BOARDS).json()[0]["id"]


# --- priority ---------------------------------------------------------------


def test_priority_defaults_to_none(client):
    card = _card(client, "no-priority")
    assert card["priority"] == "none"


def test_set_and_read_priority(client):
    card = _card(client, "urgent", priority="urgent")
    assert card["priority"] == "urgent"
    assert client.get(f"{CARDS}/{card['id']}").json()["priority"] == "urgent"


def test_update_priority(client):
    card = _card(client, "rerank")
    r = client.patch(f"{CARDS}/{card['id']}", json={"priority": "high"})
    assert r.status_code == 200, r.text
    assert r.json()["priority"] == "high"


def test_bad_priority_rejected_422(client):
    r = client.post(CARDS, json={"title": "bad", "priority": "critical"})
    assert r.status_code == 422


def test_priority_check_constraint_in_db():
    # The DB CHECK (ck_card_priority) is the last line of defence behind the schema.
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.db import engine

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    'INSERT INTO card (board_id, title, "column", position, priority) '
                    "VALUES (1, 't', 'todo', 0, 'bogus')"
                )
            )


# --- due_date ---------------------------------------------------------------


def test_set_and_clear_due_date(client):
    card = _card(client, "due", due_date="2026-08-01T00:00:00Z")
    assert card["due_date"] is not None
    # Clear it with null.
    r = client.patch(f"{CARDS}/{card['id']}", json={"due_date": None})
    assert r.status_code == 200, r.text
    assert r.json()["due_date"] is None


# --- labels: attach on create/update ----------------------------------------


def test_create_with_labels(client):
    board = _default_board(client)
    la = _label(client, board, "bug", "#ef4444")
    lb = _label(client, board, "feat", "#0ea5e9")
    card = _card(client, "tagged", label_ids=[la["id"], lb["id"]])
    names = {label["name"] for label in card["labels"]}
    assert names == {"bug", "feat"}
    # Present on a fresh read too.
    assert len(client.get(f"{CARDS}/{card['id']}").json()["labels"]) == 2


def test_update_replaces_labels(client):
    board = _default_board(client)
    la = _label(client, board, "one", "#111111")
    lb = _label(client, board, "two", "#222222")
    card = _card(client, "swap", label_ids=[la["id"]])
    r = client.patch(f"{CARDS}/{card['id']}", json={"label_ids": [lb["id"]]})
    assert r.status_code == 200, r.text
    assert [label["name"] for label in r.json()["labels"]] == ["two"]
    # Empty list clears them.
    r = client.patch(f"{CARDS}/{card['id']}", json={"label_ids": []})
    assert r.json()["labels"] == []


def test_labels_empty_when_none(client):
    card = _card(client, "plain")
    assert card["labels"] == []


def test_label_from_another_board_rejected_422(login_as):
    alice = login_as(*ALICE)  # claims the default board
    a_board = alice.get(BOARDS).json()[0]["id"]
    # A second board Alice owns, with its own label.
    other = alice.post(BOARDS, json={"name": "Other"}).json()
    other_label = alice.post(
        f"{BOARDS}/{other['id']}/labels", json={"name": "x", "color": "#000"}
    ).json()
    # Attaching the other board's label to a card on a_board is a 422.
    r = alice.post(
        CARDS, json={"title": "cross", "board_id": a_board, "label_ids": [other_label["id"]]}
    )
    assert r.status_code == 422


# --- list filters -----------------------------------------------------------


def test_filter_by_priority(client):
    _card(client, "hi", priority="high")
    _card(client, "lo", priority="low")
    r = client.get(CARDS, params={"priority": "high"})
    assert {c["title"] for c in r.json()} == {"hi"}


def test_filter_by_label(client):
    board = _default_board(client)
    la = _label(client, board, "target", "#123456")
    _card(client, "has", label_ids=[la["id"]])
    _card(client, "hasnt")
    r = client.get(CARDS, params={"label": la["id"]})
    assert {c["title"] for c in r.json()} == {"has"}


def test_filter_due_before(client):
    _card(client, "early", due_date="2026-01-01T00:00:00Z")
    _card(client, "late", due_date="2027-01-01T00:00:00Z")
    _card(client, "undated")
    r = client.get(CARDS, params={"due_before": "2026-06-01T00:00:00Z"})
    assert {c["title"] for c in r.json()} == {"early"}


def test_filter_overdue(client):
    # Past-due + not done → overdue; past-due but done → not; future → not.
    _card(client, "overdue", due_date="2020-01-01T00:00:00Z")
    _card(client, "done-past", column="done", due_date="2020-01-01T00:00:00Z")
    _card(client, "future", due_date="2099-01-01T00:00:00Z")
    r = client.get(CARDS, params={"overdue": "true"})
    assert {c["title"] for c in r.json()} == {"overdue"}


# --- label CRUD + authorization ---------------------------------------------


def test_list_labels(client):
    board = _default_board(client)
    _label(client, board, "a", "#1")
    _label(client, board, "b", "#2")
    r = client.get(f"{BOARDS}/{board}/labels")
    assert r.status_code == 200
    assert [label["name"] for label in r.json()] == ["a", "b"]


def test_create_label_empty_name_422(client):
    board = _default_board(client)
    assert client.post(
        f"{BOARDS}/{board}/labels", json={"name": "  ", "color": "#000"}
    ).status_code == 422


def test_delete_label_detaches_from_cards(client):
    board = _default_board(client)
    la = _label(client, board, "doomed", "#999")
    card = _card(client, "labelled", label_ids=[la["id"]])
    assert len(card["labels"]) == 1
    # Deleting the label cascades its card_label rows away → detached from the card.
    assert client.delete(f"/api/v1/labels/{la['id']}").status_code == 204
    assert client.get(f"{CARDS}/{card['id']}").json()["labels"] == []
    # And it's gone from the board's label list.
    assert client.get(f"{BOARDS}/{board}/labels").json() == []


def test_non_owner_cannot_touch_labels_403(login_as):
    alice = login_as(*ALICE)
    a_board = alice.get(BOARDS).json()[0]["id"]
    label = alice.post(
        f"{BOARDS}/{a_board}/labels", json={"name": "priv", "color": "#000"}
    ).json()

    bob = login_as(*BOB)  # owns nothing
    assert bob.get(f"{BOARDS}/{a_board}/labels").status_code == 403
    assert bob.post(
        f"{BOARDS}/{a_board}/labels", json={"name": "x", "color": "#000"}
    ).status_code == 403
    assert bob.delete(f"/api/v1/labels/{label['id']}").status_code == 403


def test_unauthenticated_cannot_list_labels_401(client):
    from fastapi.testclient import TestClient

    from app.main import app

    board = _default_board(client)
    with TestClient(app) as anon:
        assert anon.get(f"{BOARDS}/{board}/labels").status_code == 401
