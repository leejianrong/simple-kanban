"""Board authorization matrix (M3 V8, ADR 0013).

The V8 contract: ``/api/v1`` is auth-required and owner-scoped. Covers
claim-on-login, the owner's full lifecycle, non-owner ``403`` on every
board-scoped route, list scoping across two users, unauthenticated ``401``, and
the same-board epic-link rule. Two distinct human sessions come from the
``login_as`` factory (see conftest). Per the suite convention, app imports (none
needed here) would go inside test bodies.
"""
from __future__ import annotations

BOARDS = "/api/v1/boards"
CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")


# --- claim-on-login ----------------------------------------------------------


def test_first_login_claims_the_unclaimed_default_board(login_as):
    alice = login_as(*ALICE)
    me = alice.get("/users/me").json()
    boards = alice.get(BOARDS).json()
    assert [b["name"] for b in boards] == ["Default Board"]
    assert boards[0]["owner_id"] == me["id"]  # adopted on login (rescues prod data)


def test_second_user_does_not_claim_already_owned_boards(login_as):
    login_as(*ALICE)  # claims the default board
    bob = login_as(*BOB)  # nothing left unclaimed
    assert bob.get(BOARDS).json() == []


# --- the owner's full lifecycle ----------------------------------------------


def test_owner_can_read_write_move_delete(login_as):
    alice = login_as(*ALICE)
    bid = alice.get(BOARDS).json()[0]["id"]  # the claimed default board
    card = alice.post(CARDS, json={"title": "mine", "board_id": bid}).json()
    assert alice.get(f"{CARDS}/{card['id']}").status_code == 200
    assert alice.patch(f"{CARDS}/{card['id']}", json={"title": "edited"}).status_code == 200
    assert alice.post(f"{CARDS}/{card['id']}/move", json={"column": "done"}).status_code == 200
    assert alice.delete(f"{CARDS}/{card['id']}").status_code == 204


# --- non-owner is forbidden on every board-scoped route ----------------------


def test_non_owner_gets_403_everywhere(login_as):
    alice = login_as(*ALICE)  # claims the default board
    a_board = alice.get(BOARDS).json()[0]["id"]
    a_card = alice.post(CARDS, json={"title": "secret", "board_id": a_board}).json()
    a_epic = alice.post(EPICS, json={"name": "secret-epic", "board_id": a_board}).json()

    bob = login_as(*BOB)  # owns nothing

    # Board detail / rename / delete.
    assert bob.get(f"{BOARDS}/{a_board}").status_code == 403
    assert bob.patch(f"{BOARDS}/{a_board}", json={"name": "x"}).status_code == 403
    assert bob.delete(f"{BOARDS}/{a_board}").status_code == 403

    # Card read / edit / move / delete.
    assert bob.get(f"{CARDS}/{a_card['id']}").status_code == 403
    assert bob.patch(f"{CARDS}/{a_card['id']}", json={"title": "x"}).status_code == 403
    assert bob.post(f"{CARDS}/{a_card['id']}/move", json={"column": "done"}).status_code == 403
    assert bob.delete(f"{CARDS}/{a_card['id']}").status_code == 403

    # Epic read / edit / delete.
    assert bob.get(f"{EPICS}/{a_epic['id']}").status_code == 403
    assert bob.patch(f"{EPICS}/{a_epic['id']}", json={"name": "x"}).status_code == 403
    assert bob.delete(f"{EPICS}/{a_epic['id']}").status_code == 403

    # Listing / creating scoped to a board you don't own → 403 (not empty/allowed).
    assert bob.get(CARDS, params={"board_id": a_board}).status_code == 403
    assert bob.get(EPICS, params={"board_id": a_board}).status_code == 403
    assert bob.post(CARDS, json={"title": "x", "board_id": a_board}).status_code == 403
    assert bob.post(EPICS, json={"name": "x", "board_id": a_board}).status_code == 403


# --- list endpoints only ever show your own data -----------------------------


def test_lists_are_scoped_per_user(login_as):
    alice = login_as(*ALICE)  # owns the default board
    a_board = alice.get(BOARDS).json()[0]["id"]
    alice.post(CARDS, json={"title": "a-card", "board_id": a_board})
    alice.post(EPICS, json={"name": "a-epic", "board_id": a_board})

    bob = login_as(*BOB)
    b_board = bob.post(BOARDS, json={"name": "bob board"}).json()["id"]
    bob.post(CARDS, json={"title": "b-card", "board_id": b_board})
    bob.post(EPICS, json={"name": "b-epic", "board_id": b_board})

    # Each user's unscoped lists show only their own rows.
    assert [b["name"] for b in bob.get(BOARDS).json()] == ["bob board"]
    assert {c["title"] for c in bob.get(CARDS).json()} == {"b-card"}
    assert {e["name"] for e in bob.get(EPICS).json()} == {"b-epic"}

    assert [b["name"] for b in alice.get(BOARDS).json()] == ["Default Board"]
    assert {c["title"] for c in alice.get(CARDS).json()} == {"a-card"}
    assert {e["name"] for e in alice.get(EPICS).json()} == {"a-epic"}


# --- unauthenticated is rejected outright ------------------------------------


def test_unauthenticated_is_401(client, monkeypatch):
    monkeypatch.delenv("API_TOKENS", raising=False)
    assert client.get(BOARDS).status_code == 401
    assert client.get(CARDS).status_code == 401
    assert client.get(EPICS).status_code == 401
    assert client.post(BOARDS, json={"name": "x"}).status_code == 401


# --- one board owns its epics + stories: no cross-board links -----------------


def test_story_cannot_link_an_epic_on_another_board(login_as):
    alice = login_as(*ALICE)
    b1 = alice.get(BOARDS).json()[0]["id"]  # default board
    b2 = alice.post(BOARDS, json={"name": "second"}).json()["id"]
    epic_on_b2 = alice.post(EPICS, json={"name": "e", "board_id": b2}).json()["id"]

    # A story on b1 may not point at an epic that lives on b2.
    r = alice.post(CARDS, json={"title": "x", "board_id": b1, "epic_id": epic_on_b2})
    assert r.status_code == 422

    # Same-board link is fine; re-linking via PATCH to a foreign board is rejected.
    epic_on_b1 = alice.post(EPICS, json={"name": "e1", "board_id": b1}).json()["id"]
    card = alice.post(CARDS, json={"title": "y", "board_id": b1, "epic_id": epic_on_b1}).json()
    # Re-linking via PATCH to a foreign board's epic is rejected too.
    relink = alice.patch(f"{CARDS}/{card['id']}", json={"epic_id": epic_on_b2})
    assert relink.status_code == 422
