"""API tests for soft-delete of cards + epics (KAN-19, R5.2).

DELETE tombstones the row (sets ``deleted_at``) instead of removing it: the row
still exists in the table, but is invisible to every default read (GET-by-id 404s,
lists omit it) and to the ordering/position logic, and the DELETE response is
unchanged (204). Deleting an epic leaves its stories' ``epic_id`` intact (no
detach) — the restore path (KAN-20) depends on it.

Per CLAUDE.md (the PR #17 trap): every ``import app.*`` stays inside a test/fixture
body, never at module top.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(logged_in_client):
    """/api/v1 is owner-gated (V8): run as the board-owning session user, who owns
    the reset fixture's default board via claim-on-login."""
    return logged_in_client


def _create_card(client, **fields):
    r = client.post("/api/v1/cards", json={"title": "T", **fields})
    assert r.status_code == 201
    return r.json()


def _create_epic(client, **fields):
    r = client.post("/api/v1/epics", json={"name": "E", **fields})
    assert r.status_code == 201
    return r.json()


def _card_deleted_at(card_id: int):
    """Read the raw ``card.deleted_at`` straight from the DB (bypassing the API's
    soft-delete filter) so a test can assert the row is *tombstoned*, not gone."""
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        return conn.execute(
            text("SELECT deleted_at FROM card WHERE id = :id"), {"id": card_id}
        ).first()


def _epic_deleted_at(epic_id: int):
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        return conn.execute(
            text("SELECT deleted_at FROM epic WHERE id = :id"), {"id": epic_id}
        ).first()


# --- cards --------------------------------------------------------------------


def test_delete_card_is_soft(client):
    card = _create_card(client)
    assert client.delete(f"/api/v1/cards/{card['id']}").status_code == 204

    # Row still exists, but tombstoned.
    row = _card_deleted_at(card["id"])
    assert row is not None, "row should still exist after a soft delete"
    assert row[0] is not None, "deleted_at should be set"

    # Invisible to default reads.
    assert client.get(f"/api/v1/cards/{card['id']}").status_code == 404
    assert client.get("/api/v1/cards").json() == []


def test_soft_deleted_card_leaves_positions_untouched(client):
    a = _create_card(client, title="a", column="todo")  # position 0
    b = _create_card(client, title="b", column="todo")  # position 1
    c = _create_card(client, title="c", column="todo")  # position 2
    assert [a["position"], b["position"], c["position"]] == [0, 1, 2]

    assert client.delete(f"/api/v1/cards/{b['id']}").status_code == 204

    remaining = {x["title"]: x["position"] for x in client.get("/api/v1/cards").json()}
    # The middle card vanishes from reads; the survivors keep their positions
    # (deletes leave an intentional gap, ADR 0006 — soft delete preserves that).
    assert remaining == {"a": 0, "c": 2}


def test_new_card_after_soft_delete_ignores_tombstone_in_count(client):
    # A soft-deleted card must not inflate next_position (ordering excludes it).
    a = _create_card(client, title="a", column="todo")  # position 0
    b = _create_card(client, title="b", column="todo")  # position 1
    assert b["position"] == 1
    assert client.delete(f"/api/v1/cards/{a['id']}").status_code == 204
    # Only ``b`` (position 1) remains live → count of live cards in todo is 1.
    d = _create_card(client, title="d", column="todo")
    assert d["position"] == 1


def test_double_delete_card_404(client):
    card = _create_card(client)
    assert client.delete(f"/api/v1/cards/{card['id']}").status_code == 204
    # Second delete sees a tombstoned (invisible) row → 404.
    assert client.delete(f"/api/v1/cards/{card['id']}").status_code == 404


def test_cannot_move_soft_deleted_card(client):
    card = _create_card(client, column="todo")
    assert client.delete(f"/api/v1/cards/{card['id']}").status_code == 204
    r = client.post(
        f"/api/v1/cards/{card['id']}/move", json={"column": "done"}
    )
    assert r.status_code == 404


# --- epics --------------------------------------------------------------------


def test_delete_epic_is_soft(client):
    epic = _create_epic(client)
    assert client.delete(f"/api/v1/epics/{epic['id']}").status_code == 204

    row = _epic_deleted_at(epic["id"])
    assert row is not None, "row should still exist after a soft delete"
    assert row[0] is not None, "deleted_at should be set"

    assert client.get(f"/api/v1/epics/{epic['id']}").status_code == 404
    assert client.get("/api/v1/epics").json() == []


def test_soft_deleting_epic_keeps_card_epic_id(client):
    epic = _create_epic(client)
    card = _create_card(client, epic_id=epic["id"])
    assert card["epic_id"] == epic["id"]

    assert client.delete(f"/api/v1/epics/{epic['id']}").status_code == 204

    # The story is NOT detached — epic_id survives (KAN-20 restore depends on it),
    # even though the epic itself is now invisible to default reads.
    refetched = client.get(f"/api/v1/cards/{card['id']}").json()
    assert refetched["epic_id"] == epic["id"]
    assert client.get(f"/api/v1/epics/{epic['id']}").status_code == 404


def test_soft_deleted_blocker_drops_out_of_blocked_filter(client):
    # The ``blocked=`` list filter (SQL _blocked_predicate) must also ignore a
    # soft-deleted blocker: the blocked card becomes ready once its blocker is gone.
    blocker = _create_card(client, title="blocker", column="todo")
    blocked = _create_card(client, title="blocked", column="todo")
    r = client.post(
        f"/api/v1/cards/{blocked['id']}/dependencies",
        json={"blocker_id": blocker["id"]},
    )
    assert r.status_code == 201
    # While the blocker is live, the blocked card shows up under blocked=true.
    ids = [c["id"] for c in client.get("/api/v1/cards", params={"blocked": True}).json()]
    assert blocked["id"] in ids

    assert client.delete(f"/api/v1/cards/{blocker['id']}").status_code == 204
    # Now it is ready (blocked=false), and absent from blocked=true.
    ready = [c["id"] for c in client.get("/api/v1/cards", params={"blocked": False}).json()]
    still_blocked = [
        c["id"] for c in client.get("/api/v1/cards", params={"blocked": True}).json()
    ]
    assert blocked["id"] in ready
    assert blocked["id"] not in still_blocked


def test_cannot_link_card_to_soft_deleted_epic(client):
    epic = _create_epic(client)
    assert client.delete(f"/api/v1/epics/{epic['id']}").status_code == 204
    # A soft-deleted epic is invisible, so linking to it is a 422 (not found).
    r = client.post("/api/v1/cards", json={"title": "T", "epic_id": epic["id"]})
    assert r.status_code == 422
