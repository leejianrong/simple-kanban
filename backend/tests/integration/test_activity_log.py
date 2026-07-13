"""API tests for the activity-log write path — KAN-17 (M4 audit trail, R5.1).

Every board-domain mutation (create / update / delete / move of a card, epic or
board) must append **exactly one** ``activity`` row carrying the acting principal,
the entity, the action and a human summary. This card is the model + write path
only — there is no read API yet (KAN-18), so the tests drive mutations over the
HTTP client and then read the ``activity`` table directly through the sync engine.

Per the suite convention, all app-module imports live inside the test bodies, not
at module top (the PR #17 collection-time trap).
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"
BOARDS = "/api/v1/boards"

# The default logged-in identity (see conftest FAKE_EMAIL).
ACTOR_EMAIL = "octocat@example.com"


@pytest.fixture
def client(logged_in_client):
    """/api/v1 is owner-gated (V8); run as the board-owning session user, who owns
    the reset fixture's default board via claim-on-login."""
    return logged_in_client


def _activities(entity_type=None, entity_id=None, action=None):
    """Read activity rows straight from the DB (no read API yet), newest-last by id,
    optionally filtered. Returns a list of ORM ``Activity`` objects."""
    from app.db import SessionLocal
    from app.models import Activity

    with SessionLocal() as db:
        from sqlalchemy import select

        query = select(Activity).order_by(Activity.id)
        if entity_type is not None:
            query = query.where(Activity.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(Activity.entity_id == entity_id)
        if action is not None:
            query = query.where(Activity.action == action)
        return list(db.scalars(query).all())


# --- cards -------------------------------------------------------------------


def test_create_card_records_one_activity(client):
    card = client.post(CARDS, json={"title": "Fix login"}).json()

    rows = _activities(entity_type="card", entity_id=card["id"])
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "created"
    assert row.board_id == card["board_id"]
    assert card["ticket_number"] in row.summary
    assert "Fix login" in row.summary
    # Actor is the acting principal (user id + denormalised email label).
    assert row.actor_user_id is not None
    assert row.actor_label == ACTOR_EMAIL


def test_update_card_records_updated_activity(client):
    card = client.post(CARDS, json={"title": "before"}).json()
    r = client.patch(f"{CARDS}/{card['id']}", json={"title": "after"})
    assert r.status_code == 200, r.text

    actions = [a.action for a in _activities(entity_type="card", entity_id=card["id"])]
    assert actions == ["created", "updated"]


def test_delete_card_records_surviving_activity(client):
    card = client.post(CARDS, json={"title": "doomed"}).json()
    assert client.delete(f"{CARDS}/{card['id']}").status_code == 204

    # The board survives the card, so the 'deleted' audit row survives too
    # (entity_id is a plain int, not an FK to the gone card).
    rows = _activities(entity_type="card", entity_id=card["id"], action="deleted")
    assert len(rows) == 1
    assert card["ticket_number"] in rows[0].summary


def test_move_card_records_moved_activity(client):
    card = client.post(CARDS, json={"title": "movable", "column": "todo"}).json()
    r = client.post(f"{CARDS}/{card['id']}/move", json={"column": "in_progress"})
    assert r.status_code == 200, r.text

    moved = _activities(entity_type="card", entity_id=card["id"], action="moved")
    assert len(moved) == 1
    assert "in_progress" in moved[0].summary


def test_each_card_mutation_writes_exactly_one_row(client):
    card = client.post(CARDS, json={"title": "counted"}).json()
    client.patch(f"{CARDS}/{card['id']}", json={"title": "counted-2"})
    client.post(f"{CARDS}/{card['id']}/move", json={"column": "done"})
    client.delete(f"{CARDS}/{card['id']}")

    actions = [a.action for a in _activities(entity_type="card", entity_id=card["id"])]
    # Exactly one row per mutation, in order.
    assert actions == ["created", "updated", "moved", "deleted"]


# --- epics -------------------------------------------------------------------


def test_epic_create_update_delete_record_activities(client):
    epic = client.post(EPICS, json={"name": "Q3 goals"}).json()
    client.patch(f"{EPICS}/{epic['id']}", json={"name": "Q3 goals (revised)"})
    assert client.delete(f"{EPICS}/{epic['id']}").status_code == 204

    rows = _activities(entity_type="epic", entity_id=epic["id"])
    assert [a.action for a in rows] == ["created", "updated", "deleted"]
    assert epic["ticket_number"] in rows[0].summary
    assert rows[0].actor_label == ACTOR_EMAIL


# --- boards ------------------------------------------------------------------


def test_board_create_and_update_record_activities(client):
    board = client.post(BOARDS, json={"name": "Roadmap"}).json()
    client.patch(f"{BOARDS}/{board['id']}", json={"name": "Roadmap 2026"})

    rows = _activities(entity_type="board", entity_id=board["id"])
    assert [a.action for a in rows] == ["created", "updated"]
    assert rows[0].board_id == board["id"]
    assert "Roadmap" in rows[0].summary


def test_board_delete_cascades_its_activity_trail(client):
    """A board's whole audit trail is hard-deleted with it (ON DELETE CASCADE), so
    the 'deleted board' event is intentionally ephemeral — the delete succeeds and
    the board's activity rows (including any card/epic rows on it) are gone."""
    board = client.post(BOARDS, json={"name": "Ephemeral"}).json()
    card = client.post(CARDS, json={"title": "on-ephemeral", "board_id": board["id"]}).json()
    assert client.delete(f"{BOARDS}/{board['id']}").status_code == 204

    # Every activity row keyed to the deleted board is cascaded away.
    from app.db import SessionLocal
    from app.models import Activity

    with SessionLocal() as db:
        from sqlalchemy import select

        remaining = db.scalars(
            select(Activity).where(Activity.board_id == board["id"])
        ).all()
        assert list(remaining) == []
    # The card that lived on it left no orphaned rows either.
    assert _activities(entity_type="card", entity_id=card["id"]) == []
