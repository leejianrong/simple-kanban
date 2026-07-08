"""Board integration tests (Milestone 3 V7, ADR 0012).

Covers board CRUD, per-board scoping of cards/epics, per-board positions, cascade
delete, the default-board fallback for board-less writes, and owner capture from
the session. No authorization yet (that's V8) — any request may touch any board.

Per the suite convention, app imports live inside the test bodies.
"""
from __future__ import annotations

BOARDS = "/api/v1/boards"
CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"


# --- the default board (migration/backfill) ---------------------------------


def test_default_board_exists(client):
    # The reset fixture re-creates the migration's default board (id=1); the fresh
    # testcontainer migration itself proves the backfill (0005's NOT NULL would
    # fail if the 6 seeded cards hadn't been attached to it).
    boards = client.get(BOARDS).json()
    assert [b["name"] for b in boards] == ["Default Board"]
    assert boards[0]["owner_id"] is None  # unclaimed


def test_card_without_board_id_lands_on_default_board(client):
    default_id = client.get(BOARDS).json()[0]["id"]
    card = client.post(CARDS, json={"title": "no board given"}).json()
    assert card["board_id"] == default_id


# --- board CRUD --------------------------------------------------------------


def test_create_list_get_board(client):
    created = client.post(BOARDS, json={"name": "Marketing"})
    assert created.status_code == 201
    board = created.json()
    assert board["name"] == "Marketing"
    assert board["owner_id"] is None  # no session → unclaimed

    assert client.get(f"{BOARDS}/{board['id']}").json()["name"] == "Marketing"
    names = [b["name"] for b in client.get(BOARDS).json()]
    assert names == ["Default Board", "Marketing"]


def test_get_missing_board_404(client):
    assert client.get(f"{BOARDS}/9999").status_code == 404


def test_rename_board(client):
    bid = client.post(BOARDS, json={"name": "old"}).json()["id"]
    assert client.patch(f"{BOARDS}/{bid}", json={"name": "new"}).json()["name"] == "new"


def test_rename_board_rejects_empty(client):
    bid = client.post(BOARDS, json={"name": "keep"}).json()["id"]
    assert client.patch(f"{BOARDS}/{bid}", json={"name": "  "}).status_code == 422


def test_create_board_rejects_empty_name(client):
    assert client.post(BOARDS, json={"name": ""}).status_code == 422


# --- scoping -----------------------------------------------------------------


def test_cards_are_scoped_by_board(client):
    a = client.post(BOARDS, json={"name": "A"}).json()["id"]
    b = client.post(BOARDS, json={"name": "B"}).json()["id"]
    client.post(CARDS, json={"title": "on A", "board_id": a})
    client.post(CARDS, json={"title": "on B1", "board_id": b})
    client.post(CARDS, json={"title": "on B2", "board_id": b})

    titles_a = {c["title"] for c in client.get(CARDS, params={"board_id": a}).json()}
    titles_b = {c["title"] for c in client.get(CARDS, params={"board_id": b}).json()}
    assert titles_a == {"on A"}
    assert titles_b == {"on B1", "on B2"}


def test_epics_are_scoped_by_board(client):
    a = client.post(BOARDS, json={"name": "A"}).json()["id"]
    b = client.post(BOARDS, json={"name": "B"}).json()["id"]
    client.post(EPICS, json={"name": "epic A", "board_id": a})
    client.post(EPICS, json={"name": "epic B", "board_id": b})

    assert [e["name"] for e in client.get(EPICS, params={"board_id": a}).json()] == ["epic A"]
    assert [e["name"] for e in client.get(EPICS, params={"board_id": b}).json()] == ["epic B"]


def test_create_card_rejects_unknown_board_422(client):
    assert client.post(CARDS, json={"title": "x", "board_id": 9999}).status_code == 422


def test_create_epic_rejects_unknown_board_422(client):
    assert client.post(EPICS, json={"name": "x", "board_id": 9999}).status_code == 422


def test_positions_are_per_board(client):
    a = client.post(BOARDS, json={"name": "A"}).json()["id"]
    b = client.post(BOARDS, json={"name": "B"}).json()["id"]
    # First card in the same column on each board both start at position 0.
    ca = client.post(CARDS, json={"title": "a0", "board_id": a}).json()
    cb = client.post(CARDS, json={"title": "b0", "board_id": b}).json()
    assert ca["position"] == 0
    assert cb["position"] == 0


def test_move_reorders_only_within_its_board(client):
    a = client.post(BOARDS, json={"name": "A"}).json()["id"]
    b = client.post(BOARDS, json={"name": "B"}).json()["id"]
    # Board B has a card in "todo" at position 0.
    b_card = client.post(CARDS, json={"title": "b-todo", "board_id": b}).json()
    # Move a card on board A into "todo" — must not touch board B's positions.
    a_card = client.post(
        CARDS, json={"title": "a-ip", "board_id": a, "column": "in_progress"}
    ).json()
    client.post(f"{CARDS}/{a_card['id']}/move", json={"column": "todo"})

    assert client.get(f"{CARDS}/{b_card['id']}").json()["position"] == 0


# --- cascade delete ----------------------------------------------------------


def test_delete_board_cascades_its_cards_and_epics(client):
    bid = client.post(BOARDS, json={"name": "doomed"}).json()["id"]
    card = client.post(CARDS, json={"title": "c", "board_id": bid}).json()
    epic = client.post(EPICS, json={"name": "e", "board_id": bid}).json()

    assert client.delete(f"{BOARDS}/{bid}").status_code == 204

    assert client.get(f"{BOARDS}/{bid}").status_code == 404
    assert client.get(f"{CARDS}/{card['id']}").status_code == 404
    assert client.get(f"{EPICS}/{epic['id']}").status_code == 404


def test_delete_board_leaves_other_boards_untouched(client):
    keep = client.post(BOARDS, json={"name": "keep"}).json()["id"]
    drop = client.post(BOARDS, json={"name": "drop"}).json()["id"]
    kept_card = client.post(CARDS, json={"title": "kept", "board_id": keep}).json()
    client.post(CARDS, json={"title": "gone", "board_id": drop})

    client.delete(f"{BOARDS}/{drop}")

    assert client.get(f"{CARDS}/{kept_card['id']}").status_code == 200
    assert {c["title"] for c in client.get(CARDS, params={"board_id": keep}).json()} == {"kept"}


# --- owner capture from the session ------------------------------------------


def test_created_board_is_owned_by_the_session_user(logged_in_client):
    me = logged_in_client.get("/users/me").json()
    board = logged_in_client.post(BOARDS, json={"name": "mine"}).json()
    assert board["owner_id"] == me["id"]
