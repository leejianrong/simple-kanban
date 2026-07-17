"""API tests for the activity-feed ``actor=`` / ``action=`` filters — M5 V16
(KAN-249, the awareness dashboard's backend extension).

``GET /api/v1/boards/{id}/activity`` gained two optional filters so the dashboard
can slice the feed by *who* did *what*: ``actor`` (exact match on ``actor_label``,
an email / agent handle) and ``action`` (exact match on the verb). They AND with
each other and with the existing keyset pagination. These tests drive real
mutations (which record activity), then read the feed back through the filters and
assert the returned subset.

Per the suite convention, all ``import app.*`` live inside the test bodies, never
at module top (the PR #17 collection-time trap).
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
BOARDS = "/api/v1/boards"

FAKE_EMAIL = "octocat@example.com"
ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")


@pytest.fixture
def client(logged_in_client):
    """/api/v1 is owner-gated (V8); run as the board-owning session user, who owns
    the reset fixture's default board via claim-on-login."""
    return logged_in_client


def _activity_url(board_id: int) -> str:
    return f"{BOARDS}/{board_id}/activity"


# --- action filter -----------------------------------------------------------


def test_action_filter_returns_only_that_action(client):
    board_id = client.get(BOARDS).json()[0]["id"]
    # create → update → move, so the board has one row of each action.
    card = client.post(CARDS, json={"title": "Fix login"}).json()
    client.patch(f"{CARDS}/{card['id']}", json={"title": "Fix login flow"})
    client.post(f"{CARDS}/{card['id']}/move", json={"column": "in_progress"})

    r = client.get(_activity_url(board_id), params={"action": "moved"})
    assert r.status_code == 200, r.text
    feed = r.json()
    assert len(feed) >= 1
    assert {a["action"] for a in feed} == {"moved"}
    assert card["id"] in {a["entity_id"] for a in feed}

    # A different action returns a disjoint subset (never the moved rows).
    updated = client.get(_activity_url(board_id), params={"action": "updated"}).json()
    assert {a["action"] for a in updated} == {"updated"}


def test_unknown_action_returns_empty(client):
    board_id = client.get(BOARDS).json()[0]["id"]
    client.post(CARDS, json={"title": "seed"})
    r = client.get(_activity_url(board_id), params={"action": "teleported"})
    assert r.status_code == 200, r.text
    assert r.json() == []


# --- actor filter ------------------------------------------------------------


def test_actor_filter_scopes_to_that_actor(login_as):
    """Two distinct actors act on one board; ``actor=`` returns only that actor's
    rows (matched on the denormalised ``actor_label`` = the user's email)."""
    alice = login_as(*ALICE)  # first identity claims + owns the default board
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    # Bob needs write access to record activity — add him as an editor member.
    alice.post(f"{BOARDS}/{board_id}/members", json={"user_id": bob_id, "role": "editor"})

    alice.post(CARDS, json={"title": "alice card", "board_id": board_id})
    bob.post(CARDS, json={"title": "bob card", "board_id": board_id})

    alice_feed = alice.get(_activity_url(board_id), params={"actor": ALICE[0]}).json()
    assert len(alice_feed) >= 1
    assert {a["actor_label"] for a in alice_feed} == {ALICE[0]}

    bob_feed = alice.get(_activity_url(board_id), params={"actor": BOB[0]}).json()
    assert len(bob_feed) >= 1
    assert {a["actor_label"] for a in bob_feed} == {BOB[0]}

    # The unfiltered feed carries both actors — the filter genuinely narrows it.
    everyone = alice.get(_activity_url(board_id)).json()
    assert {ALICE[0], BOB[0]} <= {a["actor_label"] for a in everyone}


def test_unknown_actor_returns_empty(client):
    board_id = client.get(BOARDS).json()[0]["id"]
    client.post(CARDS, json={"title": "seed"})
    r = client.get(_activity_url(board_id), params={"actor": "nobody@example.com"})
    assert r.status_code == 200, r.text
    assert r.json() == []


# --- actor + action combined -------------------------------------------------


def test_actor_and_action_are_anded(client):
    board_id = client.get(BOARDS).json()[0]["id"]
    card = client.post(CARDS, json={"title": "combo"}).json()
    client.post(f"{CARDS}/{card['id']}/move", json={"column": "in_progress"})

    r = client.get(
        _activity_url(board_id),
        params={"actor": FAKE_EMAIL, "action": "moved"},
    )
    assert r.status_code == 200, r.text
    feed = r.json()
    assert len(feed) >= 1
    assert all(a["actor_label"] == FAKE_EMAIL and a["action"] == "moved" for a in feed)

    # A right actor but wrong action → empty (the AND, not an OR).
    mismatch = client.get(
        _activity_url(board_id),
        params={"actor": FAKE_EMAIL, "action": "deleted"},
    ).json()
    assert mismatch == []


# --- filters compose with pagination -----------------------------------------


def test_action_filter_paginates(client):
    board_id = client.get(BOARDS).json()[0]["id"]
    for i in range(5):
        client.post(CARDS, json={"title": f"page-{i}"})

    seen: list[int] = []
    cursor = None
    for _ in range(10):
        params = {"action": "created", "limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        r = client.get(_activity_url(board_id), params=params)
        assert r.status_code == 200, r.text
        page = r.json()
        assert all(a["action"] == "created" for a in page)
        seen.extend(a["id"] for a in page)
        cursor = r.headers.get("X-Next-Cursor")
        if len(page) < 2 or cursor is None:
            break

    # Gap-free, newest-first, and every row is a "created" row (>= the 5 we made).
    assert len(seen) == len(set(seen))
    assert seen == sorted(seen, reverse=True)
    assert len(seen) >= 5
