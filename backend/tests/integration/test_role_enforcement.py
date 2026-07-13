"""Role-based board authorization (KAN-13, ADR 0013 — the one authz layer).

Builds on V8's owner-gating: ``authorize_board`` is now role-aware. A board
member's role maps to an access level and each route demands a minimum:

- ``viewer`` → READ  — may read cards/epics/members, but not write.
- ``editor`` → WRITE — may read + create/update/move/delete cards + epics, but not
  manage the board or its members.
- ``owner`` (role) and the board OWNER (``board.owner_id``) → MANAGE — full access,
  including board rename/delete and member management.

A principal with no membership and no ownership still gets ``403`` on an existing
board; an unauthenticated request still ``401``. Two+ distinct human sessions come
from the ``login_as`` factory (see conftest). Per the suite convention, app imports
(none needed here) would live inside the test bodies.
"""
from __future__ import annotations

BOARDS = "/api/v1/boards"
CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")
CAROL = ("carol@example.com", "gh-carol")


def _members_url(board_id: int) -> str:
    return f"{BOARDS}/{board_id}/members"


def _setup_member(login_as, role: str):
    """Alice owns the default board; log Bob in and add him to it with ``role``.

    Returns ``(alice, bob, board_id, a_card, a_epic)`` where the card + epic are
    Alice's, so the member tests can exercise read/write/manage against real rows.
    """
    alice = login_as(*ALICE)  # first login claims the default board
    board_id = alice.get(BOARDS).json()[0]["id"]
    a_card = alice.post(CARDS, json={"title": "seed", "board_id": board_id}).json()
    a_epic = alice.post(EPICS, json={"name": "seed-epic", "board_id": board_id}).json()

    bob = login_as(*BOB)  # creates Bob's user, owns nothing
    added = alice.post(_members_url(board_id), json={"email": BOB[0], "role": role})
    assert added.status_code == 201
    return alice, bob, board_id, a_card, a_epic


# --- viewer: read yes, write no ----------------------------------------------


def test_viewer_can_read(login_as):
    _alice, bob, board_id, a_card, a_epic = _setup_member(login_as, "viewer")

    # Board + card + epic reads and scoped lists all succeed.
    assert bob.get(f"{BOARDS}/{board_id}").status_code == 200
    assert bob.get(f"{CARDS}/{a_card['id']}").status_code == 200
    assert bob.get(f"{EPICS}/{a_epic['id']}").status_code == 200
    assert bob.get(CARDS, params={"board_id": board_id}).status_code == 200
    assert bob.get(EPICS, params={"board_id": board_id}).status_code == 200
    # Listing members is a read (viewer or above).
    assert bob.get(_members_url(board_id)).status_code == 200


def test_viewer_cannot_write(login_as):
    _alice, bob, board_id, a_card, a_epic = _setup_member(login_as, "viewer")

    assert bob.post(CARDS, json={"title": "x", "board_id": board_id}).status_code == 403
    assert bob.patch(f"{CARDS}/{a_card['id']}", json={"title": "x"}).status_code == 403
    assert bob.post(f"{CARDS}/{a_card['id']}/move", json={"column": "done"}).status_code == 403
    assert bob.delete(f"{CARDS}/{a_card['id']}").status_code == 403
    assert bob.post(EPICS, json={"name": "x", "board_id": board_id}).status_code == 403
    assert bob.patch(f"{EPICS}/{a_epic['id']}", json={"name": "x"}).status_code == 403
    assert bob.delete(f"{EPICS}/{a_epic['id']}").status_code == 403


def test_viewer_cannot_manage(login_as):
    _alice, bob, board_id, _card, _epic = _setup_member(login_as, "viewer")

    assert bob.patch(f"{BOARDS}/{board_id}", json={"name": "x"}).status_code == 403
    assert bob.delete(f"{BOARDS}/{board_id}").status_code == 403
    assert bob.post(_members_url(board_id), json={"email": CAROL[0]}).status_code == 403


# --- editor: read + write yes, manage no -------------------------------------


def test_editor_can_read_and_write(login_as):
    _alice, bob, board_id, a_card, a_epic = _setup_member(login_as, "editor")

    # Reads.
    assert bob.get(f"{BOARDS}/{board_id}").status_code == 200
    assert bob.get(f"{CARDS}/{a_card['id']}").status_code == 200
    # Writes: create / edit / move / delete cards + epics.
    made = bob.post(CARDS, json={"title": "by-editor", "board_id": board_id})
    assert made.status_code == 201
    assert bob.patch(f"{CARDS}/{a_card['id']}", json={"title": "edited"}).status_code == 200
    assert bob.post(f"{CARDS}/{a_card['id']}/move", json={"column": "done"}).status_code == 200
    assert bob.delete(f"{CARDS}/{made.json()['id']}").status_code == 204
    epic = bob.post(EPICS, json={"name": "by-editor", "board_id": board_id})
    assert epic.status_code == 201
    assert bob.patch(f"{EPICS}/{a_epic['id']}", json={"name": "e2"}).status_code == 200
    assert bob.delete(f"{EPICS}/{epic.json()['id']}").status_code == 204


def test_editor_cannot_manage(login_as):
    alice, bob, board_id, _card, _epic = _setup_member(login_as, "editor")
    # A member row Bob might try to touch.
    carol = login_as(*CAROL)
    carol_id = carol.get("/users/me").json()["id"]
    member_id = alice.post(
        _members_url(board_id), json={"user_id": carol_id, "role": "viewer"}
    ).json()["id"]

    # Board rename / delete are owner-only.
    assert bob.patch(f"{BOARDS}/{board_id}", json={"name": "x"}).status_code == 403
    assert bob.delete(f"{BOARDS}/{board_id}").status_code == 403
    # Member management (add / change-role / remove) is owner-only.
    assert bob.post(_members_url(board_id), json={"email": CAROL[0]}).status_code == 403
    assert (
        bob.patch(f"{_members_url(board_id)}/{member_id}", json={"role": "editor"}).status_code
        == 403
    )
    assert bob.delete(f"{_members_url(board_id)}/{member_id}").status_code == 403


# --- owner-role member: full access (like the board owner) -------------------


def test_owner_role_member_can_manage(login_as):
    alice, bob, board_id, _card, _epic = _setup_member(login_as, "owner")

    # Board rename works for an owner-role member.
    assert bob.patch(f"{BOARDS}/{board_id}", json={"name": "renamed"}).status_code == 200
    # Member management works too.
    carol = login_as(*CAROL)
    carol_id = carol.get("/users/me").json()["id"]
    added = bob.post(_members_url(board_id), json={"user_id": carol_id, "role": "viewer"})
    assert added.status_code == 201
    member_id = added.json()["id"]
    assert (
        bob.patch(f"{_members_url(board_id)}/{member_id}", json={"role": "editor"}).status_code
        == 200
    )
    assert bob.delete(f"{_members_url(board_id)}/{member_id}").status_code == 204
    # And of course the board owner (via ownership) still manages.
    assert alice.delete(f"{BOARDS}/{board_id}").status_code == 204


# --- a principal with neither ownership nor membership is still forbidden -----


def test_non_member_non_owner_still_403(login_as):
    alice = login_as(*ALICE)
    board_id = alice.get(BOARDS).json()[0]["id"]
    a_card = alice.post(CARDS, json={"title": "secret", "board_id": board_id}).json()

    bob = login_as(*BOB)  # not a member, owns nothing
    assert bob.get(f"{BOARDS}/{board_id}").status_code == 403
    assert bob.get(f"{CARDS}/{a_card['id']}").status_code == 403
    assert bob.get(CARDS, params={"board_id": board_id}).status_code == 403
    assert bob.get(_members_url(board_id)).status_code == 403


# --- unauthenticated is rejected outright ------------------------------------


def test_unauthenticated_is_401(client, login_as):
    alice = login_as(*ALICE)
    board_id = alice.get(BOARDS).json()[0]["id"]
    assert client.get(f"{BOARDS}/{board_id}").status_code == 401
    assert client.get(CARDS, params={"board_id": board_id}).status_code == 401
