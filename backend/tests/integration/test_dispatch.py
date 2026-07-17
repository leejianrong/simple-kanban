"""Integration tests for dispatch + fleet-safe claim (M5 V12, KAN-245).

Exercises ``POST /boards/{id}/dispatch`` (atomic claim) and ``GET /boards/{id}/next``
(peek) against a real Postgres. The correctness crux is the **concurrency** test:
two overlapping transactions both try to claim a board's single ready card, and
``FOR UPDATE SKIP LOCKED`` guarantees exactly one wins (the other sees nothing).
The rest cover the selection rules (priority order, blocked-skip, todo-only), the
204-when-nothing-ready path, assignee defaulting, peek-doesn't-mutate, and authz.

Per the suite convention, every ``import app.*`` lives inside a test/fixture body
(never module top) so the throwaway-DB fixture repoints DATABASE_URL first.
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
BOARDS = "/api/v1/boards"


@pytest.fixture
def client(logged_in_client):
    """/api/v1 is owner-gated (V8): run as the board-owning session user, who owns
    the reset fixture's default board via claim-on-login."""
    return logged_in_client


def _board_id(client) -> int:
    return client.get(BOARDS).json()[0]["id"]


def _card(client, title="T", **fields):
    r = client.post(CARDS, json={"title": title, **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _add_dep(client, blocked_id, blocker_id):
    r = client.post(f"{CARDS}/{blocked_id}/dependencies", json={"blocker_id": blocker_id})
    assert r.status_code == 201, r.text
    return r.json()


# --- the concurrency crux: FOR UPDATE SKIP LOCKED ---------------------------


def test_concurrent_dispatch_never_double_claims(client):
    """Two overlapping transactions each try to claim the board's ONE ready card;
    ``FOR UPDATE SKIP LOCKED`` means exactly one gets it and the other gets nothing.

    Driven at the DB layer (two real sessions on the sync engine) because that is
    precisely what the endpoint's single transaction does — this proves the row
    lock/skip primitive directly and deterministically, without racing threads.
    """
    from sqlalchemy.orm import Session

    from app.db import engine
    from app.ordering import select_next_ready_card

    board = _board_id(client)
    only = _card(client, "the-one-ready-card")

    # Session A opens a transaction and locks the ready row (mimics dispatch mid-txn).
    session_a = Session(engine)
    session_b = Session(engine)
    try:
        claimed_a = select_next_ready_card(session_a, board, for_update=True)
        assert claimed_a is not None
        assert claimed_a.id == only["id"]  # A won the row and holds the lock

        # Session B runs the identical locked select while A's txn is still open.
        # SKIP LOCKED makes it skip the row A holds → nothing left to claim.
        claimed_b = select_next_ready_card(session_b, board, for_update=True)
        assert claimed_b is None  # B gets no card — no double-claim

        # A commits its claim; only then is the lock released.
        claimed_a.column = "in_progress"
        session_a.commit()
    finally:
        session_a.close()
        session_b.close()

    # After A's commit the card is in_progress; the board has nothing ready → 204.
    assert client.post(f"{BOARDS}/{board}/dispatch").status_code == 204


def test_second_sequential_dispatch_gets_204(client):
    board = _board_id(client)
    _card(client, "only-one")
    first = client.post(f"{BOARDS}/{board}/dispatch")
    assert first.status_code == 200, first.text
    assert first.json()["column"] == "in_progress"
    # The card is claimed and out of todo, so the next dispatch finds nothing.
    assert client.post(f"{BOARDS}/{board}/dispatch").status_code == 204


# --- selection rules --------------------------------------------------------


def test_dispatch_claims_moves_and_assigns(client):
    board = _board_id(client)
    card = _card(client, "work-me")
    me = client.get("/users/me").json()

    r = client.post(f"{BOARDS}/{board}/dispatch")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == card["id"]
    assert body["column"] == "in_progress"
    # Default assignee is the calling principal's identity (email).
    assert body["assignee"] == me["email"]


def test_dispatch_body_assignee_overrides_default(client):
    board = _board_id(client)
    _card(client, "work-me")
    r = client.post(f"{BOARDS}/{board}/dispatch", json={"assignee": "agent-7"})
    assert r.status_code == 200, r.text
    assert r.json()["assignee"] == "agent-7"


def test_dispatch_respects_priority_over_position(client):
    board = _board_id(client)
    # low is created first (earlier position); urgent is created later (later
    # position). Priority must win, so urgent dispatches first despite its position.
    _card(client, "low-first", priority="low")
    urgent = _card(client, "urgent-later", priority="urgent")
    r = client.post(f"{BOARDS}/{board}/dispatch")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == urgent["id"]


def test_dispatch_orders_by_position_within_same_priority(client):
    board = _board_id(client)
    first = _card(client, "pos-0")
    _card(client, "pos-1")
    r = client.post(f"{BOARDS}/{board}/dispatch")
    assert r.json()["id"] == first["id"]  # same priority → lowest position wins


def test_dispatch_skips_blocked_card(client):
    board = _board_id(client)
    # An open blocker (in_progress, so not itself a todo candidate).
    blocker = _card(client, "blocker", column="in_progress")
    blocked = _card(client, "blocked-first")  # todo, position 0
    free = _card(client, "free-second")  # todo, position 1
    _add_dep(client, blocked["id"], blocker["id"])

    r = client.post(f"{BOARDS}/{board}/dispatch")
    assert r.status_code == 200, r.text
    # Despite being earlier in position, the blocked card is skipped for the free one.
    assert r.json()["id"] == free["id"]


def test_dispatch_ready_again_when_blocker_done(client):
    board = _board_id(client)
    blocker = _card(client, "blocker", column="in_progress")
    blocked = _card(client, "blocked")
    _add_dep(client, blocked["id"], blocker["id"])
    # All todo cards are blocked → nothing ready.
    assert client.post(f"{BOARDS}/{board}/dispatch").status_code == 204
    # Complete the blocker; the blocked card becomes ready and dispatches.
    client.post(f"{CARDS}/{blocker['id']}/move", json={"column": "done"})
    r = client.post(f"{BOARDS}/{board}/dispatch")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == blocked["id"]


def test_dispatch_ignores_in_progress_and_done(client):
    board = _board_id(client)
    _card(client, "already-going", column="in_progress")
    _card(client, "already-done", column="done")
    # No todo cards → nothing to dispatch.
    assert client.post(f"{BOARDS}/{board}/dispatch").status_code == 204


def test_dispatch_empty_board_204(client):
    board = _board_id(client)
    assert client.post(f"{BOARDS}/{board}/dispatch").status_code == 204


# --- optional filters -------------------------------------------------------


def test_dispatch_priority_minimum_filter(client):
    board = _board_id(client)
    _card(client, "low", priority="low")
    high = _card(client, "high", priority="high")
    # priority=high → only cards at rank high or above are eligible.
    r = client.post(f"{BOARDS}/{board}/dispatch", json={"priority": "high"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == high["id"]
    # With only the low card left, a high-minimum dispatch finds nothing.
    assert (
        client.post(f"{BOARDS}/{board}/dispatch", json={"priority": "high"}).status_code
        == 204
    )


def test_dispatch_label_filter(client):
    board = _board_id(client)
    label = client.post(
        f"{BOARDS}/{board}/labels", json={"name": "backend", "color": "#0ea5e9"}
    ).json()
    _card(client, "unlabelled")
    tagged = _card(client, "tagged", label_ids=[label["id"]])
    r = client.post(f"{BOARDS}/{board}/dispatch", json={"label": label["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == tagged["id"]


# --- peek (next) ------------------------------------------------------------


def test_next_peeks_without_mutating(client):
    board = _board_id(client)
    card = _card(client, "peek-me", priority="high")
    r = client.get(f"{BOARDS}/{board}/next")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == card["id"]
    # Peek must not claim: the card is still in todo and unassigned.
    fresh = client.get(f"{CARDS}/{card['id']}").json()
    assert fresh["column"] == "todo"
    assert fresh["assignee"] is None


def test_next_empty_board_204(client):
    board = _board_id(client)
    assert client.get(f"{BOARDS}/{board}/next").status_code == 204


def test_next_and_dispatch_agree_on_selection(client):
    board = _board_id(client)
    _card(client, "low", priority="low")
    urgent = _card(client, "urgent", priority="urgent")
    peeked = client.get(f"{BOARDS}/{board}/next").json()
    dispatched = client.post(f"{BOARDS}/{board}/dispatch").json()
    assert peeked["id"] == dispatched["id"] == urgent["id"]


# --- authorization ----------------------------------------------------------


def test_dispatch_requires_auth(client):
    # A fresh unauthenticated client — no cookie, no PAT.
    from fastapi.testclient import TestClient

    from app.main import app

    board = _board_id(client)
    with TestClient(app) as anon:
        assert anon.post(f"{BOARDS}/{board}/dispatch").status_code == 401
        assert anon.get(f"{BOARDS}/{board}/next").status_code == 401


def test_dispatch_non_member_forbidden(login_as):
    # userA owns the default board (claim-on-login for the first identity).
    owner = login_as("owner@example.com", "gh-owner")
    board = owner.get(BOARDS).json()[0]["id"]
    owner.post(CARDS, json={"title": "theirs"})
    # userB has no access to userA's board.
    other = login_as("stranger@example.com", "gh-stranger")
    assert other.post(f"{BOARDS}/{board}/dispatch").status_code == 403
    assert other.get(f"{BOARDS}/{board}/next").status_code == 403
