"""API tests for card work-links (PR / branch / CI) — KAN-32.

Covers attaching / detaching a link, the read-side ``links`` array on both list
and detail reads, and the guards: empty label/url (422), missing card (404),
missing link (404), non-owner (403), unauthenticated (401) and cascade-delete.
Uses only the HTTP client — per the suite convention, any app-module imports go
inside test bodies, not at module top.
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
BOARDS = "/api/v1/boards"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")

PR_URL = "https://github.com/acme/repo/pull/42"
BRANCH_URL = "https://github.com/acme/repo/tree/feat/kan32"


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so these tests run as the
    board-owning session user (claim-on-login gives them the default board)."""
    return logged_in_client


def _card(client, title="T", **fields):
    r = client.post(CARDS, json={"title": title, **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _add_link(client, card_id, label="PR", url=PR_URL):
    return client.post(f"{CARDS}/{card_id}/links", json={"label": label, "url": url})


# --- add / remove happy path -------------------------------------------------


def test_add_link_reflected_on_card(client):
    card = _card(client, "with-links")

    r = _add_link(client, card["id"], "PR", PR_URL)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["links"]) == 1
    link = body["links"][0]
    assert link["label"] == "PR"
    assert link["url"] == PR_URL
    assert "id" in link and "created_at" in link


def test_add_multiple_links_ordered_by_creation(client):
    card = _card(client, "multi")
    _add_link(client, card["id"], "PR", PR_URL)
    _add_link(client, card["id"], "branch", BRANCH_URL)

    detail = client.get(f"{CARDS}/{card['id']}").json()
    labels = [link["label"] for link in detail["links"]]
    assert labels == ["PR", "branch"]  # id-ordered = creation order


def test_remove_link(client):
    card = _card(client, "removable")
    link_id = _add_link(client, card["id"]).json()["links"][0]["id"]

    r = client.delete(f"{CARDS}/{card['id']}/links/{link_id}")
    assert r.status_code == 200, r.text
    assert r.json()["links"] == []
    # And it's gone from a fresh read.
    assert client.get(f"{CARDS}/{card['id']}").json()["links"] == []


def test_remove_missing_link_404(client):
    card = _card(client, "no-link")
    r = client.delete(f"{CARDS}/{card['id']}/links/999999")
    assert r.status_code == 404


def test_remove_link_belonging_to_other_card_404(client):
    a = _card(client, "A")
    b = _card(client, "B")
    link_id = _add_link(client, a["id"]).json()["links"][0]["id"]
    # The link exists, but not on card B → 404 (not silently removed).
    r = client.delete(f"{CARDS}/{b['id']}/links/{link_id}")
    assert r.status_code == 404
    # Untouched on A.
    assert len(client.get(f"{CARDS}/{a['id']}").json()["links"]) == 1


# --- read shape: array on list + detail --------------------------------------


def test_links_present_on_list_and_detail(client):
    card = _card(client, "listed")
    _add_link(client, card["id"], "CI", "https://ci.example.com/run/7")

    detail = client.get(f"{CARDS}/{card['id']}").json()
    assert detail["links"][0]["label"] == "CI"

    # List read (populated in one grouped query, no per-card N+1).
    listed = {c["id"]: c for c in client.get(CARDS).json()}
    assert listed[card["id"]]["links"][0]["url"] == "https://ci.example.com/run/7"


def test_links_empty_when_none(client):
    card = _card(client, "lonely")
    assert card["links"] == []
    assert client.get(f"{CARDS}/{card['id']}").json()["links"] == []


# --- guards ------------------------------------------------------------------


def test_empty_label_rejected_422(client):
    card = _card(client, "bad-label")
    assert _add_link(client, card["id"], "   ", PR_URL).status_code == 422


def test_empty_url_rejected_422(client):
    card = _card(client, "bad-url")
    assert _add_link(client, card["id"], "PR", "   ").status_code == 422


def test_add_link_to_missing_card_404(client):
    r = _add_link(client, 999999)
    assert r.status_code == 404


# --- authorization -----------------------------------------------------------


def test_non_owner_cannot_touch_links_403(login_as):
    alice = login_as(*ALICE)  # claims default board
    a_board = alice.get(BOARDS).json()[0]["id"]
    card = alice.post(CARDS, json={"title": "owned", "board_id": a_board}).json()
    link_id = alice.post(
        f"{CARDS}/{card['id']}/links", json={"label": "PR", "url": PR_URL}
    ).json()["links"][0]["id"]

    bob = login_as(*BOB)  # owns nothing
    assert bob.post(
        f"{CARDS}/{card['id']}/links", json={"label": "PR", "url": PR_URL}
    ).status_code == 403
    assert bob.delete(
        f"{CARDS}/{card['id']}/links/{link_id}"
    ).status_code == 403


def test_unauthenticated_cannot_add_link_401(client):
    from fastapi.testclient import TestClient

    from app.main import app

    card = _card(client, "owned")
    with TestClient(app) as anon:
        r = anon.post(
            f"{CARDS}/{card['id']}/links", json={"label": "PR", "url": PR_URL}
        )
        assert r.status_code == 401


def test_cascade_delete_removes_links(client):
    card = _card(client, "doomed")
    _add_link(client, card["id"])
    # Deleting the card cascades its links away (ON DELETE CASCADE).
    assert client.delete(f"{CARDS}/{card['id']}").status_code == 204
    assert client.get(f"{CARDS}/{card['id']}").status_code == 404
