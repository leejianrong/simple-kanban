"""API tests for the needs-human handoff flag (M5 V13, KAN-246).

Covers the human↔agent handoff primitive: an agent flags a card ``needs-human``
(with an optional note), it surfaces under the ``needs_human=true`` list filter and
records an ``attention`` activity row; a human clears it (``/resolve``), which drops
the flag + note and records a ``resolved`` row; and the resolution *channel* — the
existing comments feature — round-trips. Authorization is owner/member-gated exactly
like the rest of ``/api/v1`` (non-member 403, unauthenticated 401), and a missing /
deleted card 404s.

Per the suite convention, every ``import app.*`` lives inside a test body / fixture,
not at module top (the PR #17 collection-time trap).
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
BOARDS = "/api/v1/boards"

ALICE = ("alice@example.com", "gh-alice")
BOB = ("bob@example.com", "gh-bob")


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so these tests run as the
    board-owning session user (claim-on-login gives them the default board)."""
    return logged_in_client


def _card(client, title="T", **fields):
    r = client.post(CARDS, json={"title": title, **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _activities(entity_id, action=None):
    """Read activity rows for one entity straight from the DB (newest-last by id),
    optionally filtered by action. Returns a list of ORM ``Activity`` objects."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Activity

    with SessionLocal() as db:
        query = (
            select(Activity)
            .where(Activity.entity_type == "card", Activity.entity_id == entity_id)
            .order_by(Activity.id)
        )
        if action is not None:
            query = query.where(Activity.action == action)
        return list(db.scalars(query).all())


# --- raise the flag ---------------------------------------------------------


def test_card_defaults_to_not_needing_a_human(client):
    card = _card(client, "fresh")
    assert card["needs_human"] is False
    assert card["attention_note"] is None


def test_raise_needs_human_with_note(client):
    card = _card(client, "stuck")
    r = client.post(
        f"{CARDS}/{card['id']}/needs-human",
        json={"attention_note": "need the prod DB password to continue"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["needs_human"] is True
    assert body["attention_note"] == "need the prod DB password to continue"
    # Persisted — a fresh read reflects it.
    got = client.get(f"{CARDS}/{card['id']}").json()
    assert got["needs_human"] is True
    assert got["attention_note"] == "need the prod DB password to continue"


def test_raise_needs_human_without_note(client):
    card = _card(client, "flag-only")
    r = client.post(f"{CARDS}/{card['id']}/needs-human", json={})
    assert r.status_code == 200, r.text
    assert r.json()["needs_human"] is True
    assert r.json()["attention_note"] is None


def test_raise_needs_human_records_attention_activity(client):
    card = _card(client, "audit")
    client.post(f"{CARDS}/{card['id']}/needs-human", json={"attention_note": "help"})
    rows = _activities(card["id"], action="attention")
    assert len(rows) == 1
    assert card["ticket_number"] in rows[0].summary
    assert rows[0].actor_user_id is not None


def test_blank_note_rejected_422(client):
    card = _card(client, "blank")
    r = client.post(
        f"{CARDS}/{card['id']}/needs-human", json={"attention_note": "   "}
    )
    assert r.status_code == 422


# --- the list filter --------------------------------------------------------


def test_needs_human_list_filter(client):
    board = client.get(BOARDS).json()[0]["id"]
    flagged = _card(client, "flagged")
    calm = _card(client, "calm")
    client.post(f"{CARDS}/{flagged['id']}/needs-human", json={"attention_note": "x"})

    ids_true = {
        c["id"] for c in client.get(f"{CARDS}?board_id={board}&needs_human=true").json()
    }
    ids_false = {
        c["id"] for c in client.get(f"{CARDS}?board_id={board}&needs_human=false").json()
    }
    assert flagged["id"] in ids_true
    assert flagged["id"] not in ids_false
    assert calm["id"] in ids_false
    assert calm["id"] not in ids_true


# --- resolve ----------------------------------------------------------------


def test_resolve_clears_flag_and_note_and_records_activity(client):
    card = _card(client, "to-resolve")
    client.post(
        f"{CARDS}/{card['id']}/needs-human", json={"attention_note": "please decide"}
    )
    r = client.post(f"{CARDS}/{card['id']}/resolve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["needs_human"] is False
    assert body["attention_note"] is None
    # A resolved activity row lands after the attention one.
    actions = [a.action for a in _activities(card["id"])]
    assert actions[-2:] == ["attention", "resolved"]


def test_resolved_card_drops_out_of_needs_human_filter(client):
    board = client.get(BOARDS).json()[0]["id"]
    card = _card(client, "round-trip")
    client.post(f"{CARDS}/{card['id']}/needs-human", json={})
    client.post(f"{CARDS}/{card['id']}/resolve")
    ids_true = {
        c["id"] for c in client.get(f"{CARDS}?board_id={board}&needs_human=true").json()
    }
    assert card["id"] not in ids_true


# --- the resolution channel: comments ---------------------------------------


def test_comment_round_trips_as_the_resolution_channel(client):
    # V13 reuses the existing comments feature as the resolution channel: an agent
    # flags, a human answers by commenting, then resolves — the agent reads the note.
    card = _card(client, "handoff")
    client.post(
        f"{CARDS}/{card['id']}/needs-human", json={"attention_note": "which region?"}
    )
    r = client.post(
        f"{CARDS}/{card['id']}/comments", json={"body": "use us-east-1"}
    )
    assert r.status_code == 201, r.text
    comments = client.get(f"{CARDS}/{card['id']}/comments").json()
    assert [c["body"] for c in comments] == ["use us-east-1"]


# --- 404s -------------------------------------------------------------------


def test_needs_human_on_missing_card_404(client):
    assert client.post(f"{CARDS}/999999/needs-human", json={}).status_code == 404
    assert client.post(f"{CARDS}/999999/resolve").status_code == 404


def test_needs_human_on_deleted_card_404(client):
    card = _card(client, "doomed")
    assert client.delete(f"{CARDS}/{card['id']}").status_code == 204
    assert client.post(f"{CARDS}/{card['id']}/needs-human", json={}).status_code == 404
    assert client.post(f"{CARDS}/{card['id']}/resolve").status_code == 404


# --- authorization ----------------------------------------------------------


def test_non_owner_cannot_flag_or_resolve_403(login_as):
    alice = login_as(*ALICE)
    a_board = alice.get(BOARDS).json()[0]["id"]
    card = alice.post(CARDS, json={"title": "priv", "board_id": a_board}).json()

    bob = login_as(*BOB)  # owns nothing on Alice's board
    assert bob.post(f"{CARDS}/{card['id']}/needs-human", json={}).status_code == 403
    assert bob.post(f"{CARDS}/{card['id']}/resolve").status_code == 403


def test_unauthenticated_cannot_flag_401(client):
    from fastapi.testclient import TestClient

    from app.main import app

    card = _card(client, "guarded")
    with TestClient(app) as anon:
        assert anon.post(f"{CARDS}/{card['id']}/needs-human", json={}).status_code == 401
        assert anon.post(f"{CARDS}/{card['id']}/resolve").status_code == 401
