"""Shared-board visibility + role-badge integration tests (KAN-15).

Owner-only list scoping (V8) is widened so a board *member* also sees the board
in ``GET /api/v1/boards`` (and its cards via ``GET /cards?board_id=X``), while a
non-member still sees neither. Each board list item carries the caller's effective
``role`` (owner → "owner", else the membership role) for the switcher's badge.

Two distinct human sessions come from the ``login_as`` factory (see conftest); the
first login claims the reset fixture's default board. Per suite convention, app
imports live inside the test bodies (none are needed here — everything is HTTP).
"""
from __future__ import annotations

BOARDS = "/api/v1/boards"
CARDS = "/api/v1/cards"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")
CAROL = ("carol@example.com", "gh-carol")


def _members_url(board_id: int) -> str:
    return f"{BOARDS}/{board_id}/members"


def test_member_sees_shared_board_with_role(login_as):
    """A viewer member sees the owner's board in their own board list, badged
    with their membership role — not the owner's."""
    alice = login_as(*ALICE)  # claims the default board
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    alice.post(_members_url(board_id), json={"user_id": bob_id, "role": "viewer"})

    listed = bob.get(BOARDS).json()
    shared = {b["id"]: b for b in listed}
    assert board_id in shared
    assert shared[board_id]["role"] == "viewer"


def test_role_reflects_membership_role(login_as):
    """The badge role tracks the member's actual role (editor here)."""
    alice = login_as(*ALICE)
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    alice.post(_members_url(board_id), json={"user_id": bob_id, "role": "editor"})

    board = next(b for b in bob.get(BOARDS).json() if b["id"] == board_id)
    assert board["role"] == "editor"


def test_owner_board_has_owner_role(login_as):
    """The owner still sees their own board, badged "owner"."""
    alice = login_as(*ALICE)
    boards = alice.get(BOARDS).json()
    assert len(boards) == 1
    assert boards[0]["role"] == "owner"


def test_non_member_does_not_see_board(login_as):
    """A user who is neither owner nor member sees none of the owner's boards."""
    alice = login_as(*ALICE)  # owns the default board
    carol = login_as(*CAROL)  # owns nothing, member of nothing
    alice_board = alice.get(BOARDS).json()[0]["id"]

    listed = carol.get(BOARDS).json()
    assert all(b["id"] != alice_board for b in listed)


def test_member_sees_shared_board_cards(login_as):
    """A member can list the shared board's cards via ?board_id."""
    alice = login_as(*ALICE)
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    created = alice.post(CARDS, json={"title": "shared-card", "board_id": board_id})
    assert created.status_code == 201
    card_id = created.json()["id"]

    alice.post(_members_url(board_id), json={"user_id": bob_id, "role": "viewer"})

    cards = bob.get(CARDS, params={"board_id": board_id}).json()
    assert any(c["id"] == card_id for c in cards)


def test_removed_member_loses_visibility(login_as):
    """Removing the membership row removes the board from the ex-member's list."""
    alice = login_as(*ALICE)
    bob = login_as(*BOB)
    bob_id = bob.get("/users/me").json()["id"]
    board_id = alice.get(BOARDS).json()[0]["id"]

    member = alice.post(
        _members_url(board_id), json={"user_id": bob_id, "role": "viewer"}
    ).json()
    assert any(b["id"] == board_id for b in bob.get(BOARDS).json())

    alice.delete(f"{_members_url(board_id)}/{member['id']}")
    assert all(b["id"] != board_id for b in bob.get(BOARDS).json())
