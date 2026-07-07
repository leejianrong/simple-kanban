"""API tests for GET-one / PATCH / DELETE (Slice 2).

Covers reading one card, field edits (partial, clearing nullables, validation,
non-editable fields), hard delete (incl. the intentional position gap and
non-reuse of ticket numbers), and 404s for missing cards.
"""
from __future__ import annotations


def _create(client, **fields):
    payload = {"title": "T", **fields}
    r = client.post("/api/cards", json=payload)
    assert r.status_code == 201
    return r.json()


# --- GET /api/cards/{id} ---------------------------------------------------


def test_get_card_by_id(client):
    created = _create(client, title="Read me", assignee="Jian")
    r = client.get(f"/api/cards/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_missing_card_404(client):
    assert client.get("/api/cards/999").status_code == 404


# --- PATCH /api/cards/{id} -------------------------------------------------


def test_patch_updates_fields(client):
    card = _create(client, title="Before", story_points=1)
    r = client.patch(
        f"/api/cards/{card['id']}",
        json={"title": "After", "story_points": 8},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "After"
    assert body["story_points"] == 8
    assert body["updated_at"] >= body["created_at"]


def test_patch_is_partial(client):
    card = _create(client, title="Keep desc", description="original", assignee="Jian")
    r = client.patch(f"/api/cards/{card['id']}", json={"title": "New title"})
    body = r.json()
    assert body["title"] == "New title"
    # Untouched fields are preserved.
    assert body["description"] == "original"
    assert body["assignee"] == "Jian"


def test_patch_can_clear_nullable_fields(client):
    card = _create(client, assignee="Jian", story_points=5, description="d")
    r = client.patch(
        f"/api/cards/{card['id']}",
        json={"assignee": None, "story_points": None, "description": None},
    )
    body = r.json()
    assert body["assignee"] is None
    assert body["story_points"] is None
    assert body["description"] is None


def test_patch_rejects_empty_or_null_title(client):
    card = _create(client)
    assert client.patch(f"/api/cards/{card['id']}", json={"title": ""}).status_code == 422
    assert client.patch(f"/api/cards/{card['id']}", json={"title": "   "}).status_code == 422
    assert client.patch(f"/api/cards/{card['id']}", json={"title": None}).status_code == 422


def test_patch_rejects_bad_story_points(client):
    card = _create(client)
    assert client.patch(f"/api/cards/{card['id']}", json={"story_points": 4}).status_code == 422


def test_patch_ignores_non_editable_fields(client):
    card = _create(client, column="todo")
    r = client.patch(
        f"/api/cards/{card['id']}",
        json={
            "title": "Edited",
            "column": "done",          # not an editable field — ignored
            "ticket_number": "KAN-999", # server-owned — ignored
            "position": 42,             # server-owned — ignored
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Edited"
    assert body["column"] == "todo"          # unchanged (move is via /move)
    assert body["ticket_number"] == card["ticket_number"]
    assert body["position"] == card["position"]


def test_patch_missing_card_404(client):
    assert client.patch("/api/cards/999", json={"title": "x"}).status_code == 404


# --- DELETE /api/cards/{id} ------------------------------------------------


def test_delete_removes_card(client):
    card = _create(client)
    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    assert client.get(f"/api/cards/{card['id']}").status_code == 404
    assert client.get("/api/cards").json() == []


def test_delete_missing_card_404(client):
    assert client.delete("/api/cards/999").status_code == 404


def test_delete_leaves_position_gap(client):
    a = _create(client, title="a", column="todo")  # position 0
    b = _create(client, title="b", column="todo")  # position 1
    c = _create(client, title="c", column="todo")  # position 2
    assert [a["position"], b["position"], c["position"]] == [0, 1, 2]

    assert client.delete(f"/api/cards/{b['id']}").status_code == 204

    remaining = {x["title"]: x["position"] for x in client.get("/api/cards").json()}
    # Positions are a relative sort key; deleting the middle leaves a gap (0, 2).
    assert remaining == {"a": 0, "c": 2}


def test_ticket_numbers_not_reused_after_delete(client):
    first = _create(client)
    assert first["ticket_number"] == "KAN-1"
    assert client.delete(f"/api/cards/{first['id']}").status_code == 204
    second = _create(client)
    # Sequence is monotonic — the next card is KAN-2, not KAN-1 again.
    assert second["ticket_number"] == "KAN-2"
