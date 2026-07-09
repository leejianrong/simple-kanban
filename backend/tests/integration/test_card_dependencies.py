"""API tests for card-to-card dependencies (KAN-28).

Covers adding / removing a blocker, the read-side ``blocked_by`` / ``blocks``
arrays on both list and detail reads, and every guard: self-link, cross-board,
duplicate, cycle (all 422), missing card (404) and non-owner (403). Uses only the
HTTP client — per the suite convention, any app-module imports go inside test
bodies, not at module top.
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


def _add_dep(client, blocked_id, blocker_id):
    """Record that ``blocked_id`` is blocked-by ``blocker_id``."""
    return client.post(f"{CARDS}/{blocked_id}/dependencies", json={"blocker_id": blocker_id})


# --- add / remove happy path -------------------------------------------------


def test_add_blocker_reflected_on_both_cards(client):
    blocker = _card(client, "blocker")
    blocked = _card(client, "blocked")

    r = _add_dep(client, blocked["id"], blocker["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    # The returned (blocked) card is blocked-by the blocker.
    assert body["blocked_by"] == [blocker["id"]]
    assert body["blocks"] == []

    # The blocker card sees the reverse edge.
    blocker_read = client.get(f"{CARDS}/{blocker['id']}").json()
    assert blocker_read["blocks"] == [blocked["id"]]
    assert blocker_read["blocked_by"] == []


def test_remove_blocker(client):
    blocker = _card(client, "blocker")
    blocked = _card(client, "blocked")
    _add_dep(client, blocked["id"], blocker["id"])

    r = client.delete(f"{CARDS}/{blocked['id']}/dependencies/{blocker['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["blocked_by"] == []
    # And the reverse edge is gone too.
    assert client.get(f"{CARDS}/{blocker['id']}").json()["blocks"] == []


def test_remove_missing_edge_404(client):
    blocker = _card(client, "blocker")
    blocked = _card(client, "blocked")
    # No edge added yet.
    r = client.delete(f"{CARDS}/{blocked['id']}/dependencies/{blocker['id']}")
    assert r.status_code == 404


# --- read shape: arrays on list + detail -------------------------------------


def test_arrays_present_on_list_and_detail(client):
    blocker = _card(client, "blocker")
    blocked = _card(client, "blocked")
    _add_dep(client, blocked["id"], blocker["id"])

    # Detail read.
    detail = client.get(f"{CARDS}/{blocked['id']}").json()
    assert detail["blocked_by"] == [blocker["id"]]

    # List read (arrays populated in one grouped query, no per-card N+1).
    listed = {c["id"]: c for c in client.get(CARDS).json()}
    assert listed[blocked["id"]]["blocked_by"] == [blocker["id"]]
    assert listed[blocked["id"]]["blocks"] == []
    assert listed[blocker["id"]]["blocks"] == [blocked["id"]]
    assert listed[blocker["id"]]["blocked_by"] == []


def test_arrays_empty_when_no_dependencies(client):
    card = _card(client, "lonely")
    assert card["blocked_by"] == []
    assert card["blocks"] == []
    assert client.get(f"{CARDS}/{card['id']}").json()["blocked_by"] == []


# --- guards ------------------------------------------------------------------


def test_self_link_rejected_422(client):
    card = _card(client, "self")
    r = _add_dep(client, card["id"], card["id"])
    assert r.status_code == 422


def test_missing_blocker_card_404(client):
    blocked = _card(client, "blocked")
    r = _add_dep(client, blocked["id"], 999999)
    assert r.status_code == 404


def test_missing_blocked_card_404(client):
    blocker = _card(client, "blocker")
    r = _add_dep(client, 999999, blocker["id"])
    assert r.status_code == 404


def test_duplicate_dependency_rejected_422(client):
    blocker = _card(client, "blocker")
    blocked = _card(client, "blocked")
    assert _add_dep(client, blocked["id"], blocker["id"]).status_code == 201
    # Adding the same edge again is rejected (documented behaviour: not idempotent).
    assert _add_dep(client, blocked["id"], blocker["id"]).status_code == 422


def test_cross_board_dependency_rejected_422(client):
    b1 = client.get(BOARDS).json()[0]["id"]  # default board
    b2 = client.post(BOARDS, json={"name": "second"}).json()["id"]
    a = _card(client, "on-b1", board_id=b1)
    b = _card(client, "on-b2", board_id=b2)
    r = _add_dep(client, a["id"], b["id"])
    assert r.status_code == 422


def test_direct_cycle_rejected_422(client):
    # A blocks B; then B blocks A would close a 2-cycle.
    a = _card(client, "A")
    b = _card(client, "B")
    assert _add_dep(client, b["id"], a["id"]).status_code == 201  # A blocks B
    r = _add_dep(client, a["id"], b["id"])  # B blocks A → cycle
    assert r.status_code == 422


def test_transitive_cycle_rejected_422(client):
    # A→B→C (blocks chain); C→A would close a 3-cycle.
    a = _card(client, "A")
    b = _card(client, "B")
    c = _card(client, "C")
    assert _add_dep(client, b["id"], a["id"]).status_code == 201  # A blocks B
    assert _add_dep(client, c["id"], b["id"]).status_code == 201  # B blocks C
    r = _add_dep(client, a["id"], c["id"])  # C blocks A → transitive cycle
    assert r.status_code == 422


def test_diamond_is_allowed_not_a_cycle(client):
    # A blocks B and C; both B and C block D. A DAG (diamond), not a cycle.
    a = _card(client, "A")
    b = _card(client, "B")
    c = _card(client, "C")
    d = _card(client, "D")
    assert _add_dep(client, b["id"], a["id"]).status_code == 201
    assert _add_dep(client, c["id"], a["id"]).status_code == 201
    assert _add_dep(client, d["id"], b["id"]).status_code == 201
    assert _add_dep(client, d["id"], c["id"]).status_code == 201
    assert sorted(client.get(f"{CARDS}/{d['id']}").json()["blocked_by"]) == sorted(
        [b["id"], c["id"]]
    )


# --- authorization -----------------------------------------------------------


def test_non_owner_cannot_touch_dependencies_403(login_as):
    alice = login_as(*ALICE)  # claims default board
    a_board = alice.get(BOARDS).json()[0]["id"]
    blocker = alice.post(CARDS, json={"title": "blocker", "board_id": a_board}).json()
    blocked = alice.post(CARDS, json={"title": "blocked", "board_id": a_board}).json()

    bob = login_as(*BOB)  # owns nothing
    assert bob.post(
        f"{CARDS}/{blocked['id']}/dependencies", json={"blocker_id": blocker["id"]}
    ).status_code == 403
    assert bob.delete(
        f"{CARDS}/{blocked['id']}/dependencies/{blocker['id']}"
    ).status_code == 403


def test_unauthenticated_cannot_add_dependency_401(client, login_as):
    # Create as the owner, then hit the endpoint with a fresh unauthenticated client.
    from fastapi.testclient import TestClient

    from app.main import app

    blocker = _card(client, "blocker")
    blocked = _card(client, "blocked")
    with TestClient(app) as anon:
        r = anon.post(
            f"{CARDS}/{blocked['id']}/dependencies", json={"blocker_id": blocker["id"]}
        )
        assert r.status_code == 401


def test_cascade_delete_removes_edges(client):
    blocker = _card(client, "blocker")
    blocked = _card(client, "blocked")
    _add_dep(client, blocked["id"], blocker["id"])
    # Deleting the blocker card cascades the edge away (ON DELETE CASCADE).
    assert client.delete(f"{CARDS}/{blocker['id']}").status_code == 204
    assert client.get(f"{CARDS}/{blocked['id']}").json()["blocked_by"] == []
