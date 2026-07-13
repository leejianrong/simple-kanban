"""Board-membership CRUD integration tests (KAN-12).

Covers the owner managing members (add by email + by user_id, list, change role,
remove), the duplicate/unknown-user error cases, non-owner ``403`` on every route,
and unauthenticated ``401``. Two distinct human sessions come from the ``login_as``
factory (see conftest).

These tests assert the management API (owner manages members; a *non-member*
non-owner is ``403``). Role-based access for members themselves (a viewer/editor
reading or writing the board) is covered by ``test_role_enforcement.py`` (KAN-13).

Per the suite convention, app imports live inside the test bodies.
"""
from __future__ import annotations

BOARDS = "/api/v1/boards"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")
CAROL = ("carol@example.com", "gh-carol")


def _members_url(board_id: int) -> str:
    return f"{BOARDS}/{board_id}/members"


# --- owner can manage members ------------------------------------------------


def test_owner_adds_member_by_email(login_as):
    alice = login_as(*ALICE)  # claims default board
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    r = alice.post(_members_url(board_id), json={"email": BOB[0], "role": "editor"})
    assert r.status_code == 201
    member = r.json()
    assert member["user_id"] == bob_id
    assert member["email"] == BOB[0]
    assert member["role"] == "editor"
    assert member["board_id"] == board_id


def test_owner_adds_member_by_user_id_default_role_viewer(login_as):
    alice = login_as(*ALICE)
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    r = alice.post(_members_url(board_id), json={"user_id": bob_id})
    assert r.status_code == 201
    assert r.json()["role"] == "viewer"  # default


def test_email_lookup_is_case_insensitive(login_as):
    alice = login_as(*ALICE)
    login_as(*BOB)
    board_id = alice.get(BOARDS).json()[0]["id"]

    r = alice.post(_members_url(board_id), json={"email": BOB[0].upper()})
    assert r.status_code == 201
    assert r.json()["email"] == BOB[0]


def test_list_members(login_as):
    alice = login_as(*ALICE)
    bob = login_as(*BOB)
    carol = login_as(*CAROL)
    bob_id = bob.get("/users/me").json()["id"]
    carol_id = carol.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    alice.post(_members_url(board_id), json={"user_id": bob_id, "role": "viewer"})
    alice.post(_members_url(board_id), json={"user_id": carol_id, "role": "editor"})

    listed = alice.get(_members_url(board_id)).json()
    assert {m["email"] for m in listed} == {BOB[0], CAROL[0]}
    assert {m["email"]: m["role"] for m in listed} == {
        BOB[0]: "viewer",
        CAROL[0]: "editor",
    }


def test_change_member_role(login_as):
    alice = login_as(*ALICE)
    login_as(*BOB)
    board_id = alice.get(BOARDS).json()[0]["id"]
    member_id = alice.post(
        _members_url(board_id), json={"email": BOB[0], "role": "viewer"}
    ).json()["id"]

    r = alice.patch(f"{_members_url(board_id)}/{member_id}", json={"role": "editor"})
    assert r.status_code == 200
    assert r.json()["role"] == "editor"


def test_remove_member(login_as):
    alice = login_as(*ALICE)
    login_as(*BOB)
    board_id = alice.get(BOARDS).json()[0]["id"]
    member_id = alice.post(
        _members_url(board_id), json={"email": BOB[0]}
    ).json()["id"]

    assert alice.delete(f"{_members_url(board_id)}/{member_id}").status_code == 204
    assert alice.get(_members_url(board_id)).json() == []


# --- error cases -------------------------------------------------------------


def test_add_unknown_user_404(login_as):
    alice = login_as(*ALICE)
    board_id = alice.get(BOARDS).json()[0]["id"]
    assert (
        alice.post(_members_url(board_id), json={"email": "nobody@example.com"}).status_code
        == 404
    )


def test_add_duplicate_member_409(login_as):
    alice = login_as(*ALICE)
    login_as(*BOB)
    board_id = alice.get(BOARDS).json()[0]["id"]
    assert alice.post(_members_url(board_id), json={"email": BOB[0]}).status_code == 201
    assert alice.post(_members_url(board_id), json={"email": BOB[0]}).status_code == 409


def test_add_member_requires_exactly_one_identity(login_as):
    alice = login_as(*ALICE)
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]
    # Neither identity → 422.
    assert alice.post(_members_url(board_id), json={"role": "viewer"}).status_code == 422
    # Both identities → 422.
    assert (
        alice.post(
            _members_url(board_id), json={"email": BOB[0], "user_id": bob_id}
        ).status_code
        == 422
    )


def test_invalid_role_422(login_as):
    alice = login_as(*ALICE)
    login_as(*BOB)
    board_id = alice.get(BOARDS).json()[0]["id"]
    assert (
        alice.post(_members_url(board_id), json={"email": BOB[0], "role": "admin"}).status_code
        == 422
    )


def test_patch_or_delete_unknown_member_404(login_as):
    alice = login_as(*ALICE)
    board_id = alice.get(BOARDS).json()[0]["id"]
    assert (
        alice.patch(f"{_members_url(board_id)}/9999", json={"role": "editor"}).status_code
        == 404
    )
    assert alice.delete(f"{_members_url(board_id)}/9999").status_code == 404


def test_member_of_another_board_is_404_here(login_as):
    """A member id that belongs to a different board is not found under this board."""
    alice = login_as(*ALICE)
    login_as(*BOB)
    b1 = alice.get(BOARDS).json()[0]["id"]
    b2 = alice.post(BOARDS, json={"name": "second"}).json()["id"]
    member_id = alice.post(_members_url(b1), json={"email": BOB[0]}).json()["id"]

    # The member exists on b1, so under b2 it must 404 (not leak / act cross-board).
    patch = alice.patch(f"{_members_url(b2)}/{member_id}", json={"role": "editor"})
    assert patch.status_code == 404
    assert alice.delete(f"{_members_url(b2)}/{member_id}").status_code == 404


# --- non-owner is forbidden --------------------------------------------------


def test_non_owner_gets_403_on_every_member_route(login_as):
    alice = login_as(*ALICE)  # owns the default board
    board_id = alice.get(BOARDS).json()[0]["id"]
    carol = login_as(*CAROL)
    carol_id = carol.get("/users/me").json()["id"]
    member_id = alice.post(
        _members_url(board_id), json={"user_id": carol_id}
    ).json()["id"]

    bob = login_as(*BOB)  # owns nothing on alice's board
    assert bob.get(_members_url(board_id)).status_code == 403
    assert bob.post(_members_url(board_id), json={"email": BOB[0]}).status_code == 403
    assert (
        bob.patch(f"{_members_url(board_id)}/{member_id}", json={"role": "editor"}).status_code
        == 403
    )
    assert bob.delete(f"{_members_url(board_id)}/{member_id}").status_code == 403


# --- unauthenticated is rejected outright ------------------------------------


def test_unauthenticated_is_401(client, login_as):
    alice = login_as(*ALICE)
    board_id = alice.get(BOARDS).json()[0]["id"]
    assert client.get(_members_url(board_id)).status_code == 401
    assert client.post(_members_url(board_id), json={"email": BOB[0]}).status_code == 401
    assert client.patch(f"{_members_url(board_id)}/1", json={"role": "editor"}).status_code == 401
    assert client.delete(f"{_members_url(board_id)}/1").status_code == 401
