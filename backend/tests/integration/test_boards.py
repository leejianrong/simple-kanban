"""Board integration tests (M3 V7, ADR 0012; owner-gated since V8, ADR 0013).

Covers board CRUD, per-board scoping of cards/epics, per-board positions, cascade
delete, the default-board fallback for board-less writes, and owner capture from
the session — all now exercised **as the board-owning session user**
(``logged_in_client``, which owns the reset fixture's default board via
claim-on-login). The V8 authorization matrix (401/403/list-scoping across users)
lives in test_authz.py.

Per the suite convention, app imports live inside the test bodies.
"""
from __future__ import annotations

BOARDS = "/api/v1/boards"
CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"


# --- the default board (migration/backfill) ---------------------------------


def test_default_board_exists_and_is_unclaimed():
    # Observed directly in the DB (no human has logged in, so the default board is
    # still unclaimed; V10 removed the SERVICE principal that used to observe it via
    # the API). The fresh testcontainer migration itself proves the backfill (0005's
    # NOT NULL would fail if the seeded cards weren't attached).
    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name, owner_id FROM board ORDER BY id")).all()
    assert [name for name, _ in rows] == ["Default Board"]
    assert rows[0][1] is None  # unclaimed until a human logs in


def test_card_without_board_id_lands_on_default_board(logged_in_client):
    default_id = logged_in_client.get(BOARDS).json()[0]["id"]
    card = logged_in_client.post(CARDS, json={"title": "no board given"}).json()
    assert card["board_id"] == default_id


# --- board CRUD --------------------------------------------------------------


def test_create_list_get_board(logged_in_client):
    me = logged_in_client.get("/users/me").json()
    created = logged_in_client.post(BOARDS, json={"name": "Marketing"})
    assert created.status_code == 201
    board = created.json()
    assert board["name"] == "Marketing"
    assert board["owner_id"] == me["id"]  # owner captured from the session

    assert logged_in_client.get(f"{BOARDS}/{board['id']}").json()["name"] == "Marketing"
    # The default board was claimed on login, so the owner sees both.
    names = [b["name"] for b in logged_in_client.get(BOARDS).json()]
    assert names == ["Default Board", "Marketing"]


def test_get_missing_board_404(logged_in_client):
    assert logged_in_client.get(f"{BOARDS}/9999").status_code == 404


def test_rename_board(logged_in_client):
    bid = logged_in_client.post(BOARDS, json={"name": "old"}).json()["id"]
    assert logged_in_client.patch(f"{BOARDS}/{bid}", json={"name": "new"}).json()["name"] == "new"


def test_rename_board_rejects_empty(logged_in_client):
    bid = logged_in_client.post(BOARDS, json={"name": "keep"}).json()["id"]
    assert logged_in_client.patch(f"{BOARDS}/{bid}", json={"name": "  "}).status_code == 422


def test_create_board_rejects_empty_name(logged_in_client):
    assert logged_in_client.post(BOARDS, json={"name": ""}).status_code == 422


# --- scoping (all boards owned by the same session user) ---------------------


def test_cards_are_scoped_by_board(logged_in_client):
    c = logged_in_client
    a = c.post(BOARDS, json={"name": "A"}).json()["id"]
    b = c.post(BOARDS, json={"name": "B"}).json()["id"]
    c.post(CARDS, json={"title": "on A", "board_id": a})
    c.post(CARDS, json={"title": "on B1", "board_id": b})
    c.post(CARDS, json={"title": "on B2", "board_id": b})

    titles_a = {x["title"] for x in c.get(CARDS, params={"board_id": a}).json()}
    titles_b = {x["title"] for x in c.get(CARDS, params={"board_id": b}).json()}
    assert titles_a == {"on A"}
    assert titles_b == {"on B1", "on B2"}


def test_epics_are_scoped_by_board(logged_in_client):
    c = logged_in_client
    a = c.post(BOARDS, json={"name": "A"}).json()["id"]
    b = c.post(BOARDS, json={"name": "B"}).json()["id"]
    c.post(EPICS, json={"name": "epic A", "board_id": a})
    c.post(EPICS, json={"name": "epic B", "board_id": b})

    assert [e["name"] for e in c.get(EPICS, params={"board_id": a}).json()] == ["epic A"]
    assert [e["name"] for e in c.get(EPICS, params={"board_id": b}).json()] == ["epic B"]


def test_create_card_rejects_unknown_board_422(logged_in_client):
    assert logged_in_client.post(CARDS, json={"title": "x", "board_id": 9999}).status_code == 422


def test_create_epic_rejects_unknown_board_422(logged_in_client):
    assert logged_in_client.post(EPICS, json={"name": "x", "board_id": 9999}).status_code == 422


def test_positions_are_per_board(logged_in_client):
    c = logged_in_client
    a = c.post(BOARDS, json={"name": "A"}).json()["id"]
    b = c.post(BOARDS, json={"name": "B"}).json()["id"]
    ca = c.post(CARDS, json={"title": "a0", "board_id": a}).json()
    cb = c.post(CARDS, json={"title": "b0", "board_id": b}).json()
    assert ca["position"] == 0
    assert cb["position"] == 0


def test_move_reorders_only_within_its_board(logged_in_client):
    c = logged_in_client
    a = c.post(BOARDS, json={"name": "A"}).json()["id"]
    b = c.post(BOARDS, json={"name": "B"}).json()["id"]
    b_card = c.post(CARDS, json={"title": "b-todo", "board_id": b}).json()
    a_card = c.post(
        CARDS, json={"title": "a-ip", "board_id": a, "column": "in_progress"}
    ).json()
    c.post(f"{CARDS}/{a_card['id']}/move", json={"column": "todo"})

    assert c.get(f"{CARDS}/{b_card['id']}").json()["position"] == 0


# --- cascade delete ----------------------------------------------------------


def test_delete_board_cascades_its_cards_and_epics(logged_in_client):
    c = logged_in_client
    bid = c.post(BOARDS, json={"name": "doomed"}).json()["id"]
    card = c.post(CARDS, json={"title": "c", "board_id": bid}).json()
    epic = c.post(EPICS, json={"name": "e", "board_id": bid}).json()

    assert c.delete(f"{BOARDS}/{bid}").status_code == 204

    assert c.get(f"{BOARDS}/{bid}").status_code == 404
    assert c.get(f"{CARDS}/{card['id']}").status_code == 404
    assert c.get(f"{EPICS}/{epic['id']}").status_code == 404


def test_delete_board_leaves_other_boards_untouched(logged_in_client):
    c = logged_in_client
    keep = c.post(BOARDS, json={"name": "keep"}).json()["id"]
    drop = c.post(BOARDS, json={"name": "drop"}).json()["id"]
    kept_card = c.post(CARDS, json={"title": "kept", "board_id": keep}).json()
    c.post(CARDS, json={"title": "gone", "board_id": drop})

    c.delete(f"{BOARDS}/{drop}")

    assert c.get(f"{CARDS}/{kept_card['id']}").status_code == 200
    assert {x["title"] for x in c.get(CARDS, params={"board_id": keep}).json()} == {"kept"}
