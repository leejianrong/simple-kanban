"""API tests for atomic batch card update (M5 V19, KAN-252).

``PATCH /api/v1/cards/batch`` patches several cards in one transaction — all-or-
nothing: any missing id 404s and no card changes; duplicate ids 422; an empty body
422; column/position are not editable (the move-vs-edit split). Board-scoped + auth-
gated. Per the suite convention, any app-module imports go inside test bodies, not at
module top (the PR #17 trap)."""
from __future__ import annotations

import pytest


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so run as the board-owning session user
    (shadows conftest's unauthenticated ``client``). Claim-on-login makes this user
    own the reset fixture's default board (id=1)."""
    return logged_in_client


CARDS = "/api/v1/cards"
BATCH = "/api/v1/cards/batch"


def _create(client, **fields):
    return client.post(CARDS, json={"title": "T", **fields}).json()


def test_batch_update_applies_all_atomically(client):
    a = _create(client, title="a")
    b = _create(client, title="b")
    r = client.patch(
        BATCH,
        json=[
            {"id": a["id"], "assignee": "agent-1", "priority": "high"},
            {"id": b["id"], "title": "b-renamed"},
        ],
    )
    assert r.status_code == 200
    by_id = {c["id"]: c for c in r.json()}
    assert by_id[a["id"]]["assignee"] == "agent-1"
    assert by_id[a["id"]]["priority"] == "high"
    assert by_id[b["id"]]["title"] == "b-renamed"
    # Persisted (a fresh read agrees).
    assert client.get(f"{CARDS}/{a['id']}").json()["assignee"] == "agent-1"
    assert client.get(f"{CARDS}/{b['id']}").json()["title"] == "b-renamed"


def test_batch_update_is_all_or_nothing_on_a_bad_id(client):
    a = _create(client, title="a", assignee="orig")
    # Second entry names a non-existent card → the whole batch 404s and rolls back.
    r = client.patch(
        BATCH,
        json=[
            {"id": a["id"], "assignee": "changed"},
            {"id": 9_999_999, "assignee": "x"},
        ],
    )
    assert r.status_code == 404
    # The valid card's edit was NOT applied (atomic rollback).
    assert client.get(f"{CARDS}/{a['id']}").json()["assignee"] == "orig"


def test_batch_update_rejects_duplicate_ids(client):
    a = _create(client, title="a")
    r = client.patch(
        BATCH, json=[{"id": a["id"], "assignee": "x"}, {"id": a["id"], "assignee": "y"}]
    )
    assert r.status_code == 422


def test_batch_update_rejects_empty_body(client):
    assert client.patch(BATCH, json=[]).status_code == 422


def test_batch_update_rejects_blank_title(client):
    a = _create(client, title="a")
    b = _create(client, title="b", assignee="orig")
    r = client.patch(
        BATCH, json=[{"id": a["id"], "title": "ok"}, {"id": b["id"], "title": "  "}]
    )
    assert r.status_code == 422
    # Atomic: the first card's title was not changed either.
    assert client.get(f"{CARDS}/{a['id']}").json()["title"] == "a"


def test_batch_update_ignores_column_position(client):
    # CardBatchUpdateItem carries no column/position, so a stray one is ignored — the
    # card stays put (moves go through /move, ADR 0006).
    a = _create(client, title="a")
    r = client.patch(BATCH, json=[{"id": a["id"], "column": "done", "assignee": "x"}])
    assert r.status_code == 200
    assert r.json()[0]["column"] == "todo"
    assert r.json()[0]["assignee"] == "x"


def test_batch_update_cross_board_is_forbidden(client, login_as):
    a = _create(client, title="a")
    # A stranger owns their own board but not board 1 → their batch touching card `a`
    # is a 403, and card `a` is unchanged.
    stranger = login_as("stranger@example.com", "gh-stranger")
    r = stranger.patch(BATCH, json=[{"id": a["id"], "assignee": "x"}])
    assert r.status_code == 403
    assert client.get(f"{CARDS}/{a['id']}").json().get("assignee") is None
