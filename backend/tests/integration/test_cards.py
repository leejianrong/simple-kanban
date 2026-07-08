"""API tests for the endpoints that exist today: GET /api/v1/cards, POST /api/v1/cards.

Covers listing, creation, ticket-number assignment, append positioning, and
validation. CRUD (PATCH/DELETE), move/reorder, and 404 cases get their own tests
as those slices land.
"""
from __future__ import annotations


def test_list_empty(client):
    r = client.get("/api/v1/cards")
    assert r.status_code == 200
    assert r.json() == []


def test_create_card_minimal_defaults(client):
    r = client.post("/api/v1/cards", json={"title": "First card"})
    assert r.status_code == 201
    body = r.json()
    assert body["ticket_number"] == "KAN-1"
    assert body["title"] == "First card"
    assert body["column"] == "todo"  # default column
    assert body["position"] == 0
    assert body["description"] is None
    assert body["story_points"] is None
    assert body["assignee"] is None
    assert body["id"] >= 1
    assert body["created_at"] and body["updated_at"]


def test_create_card_all_fields(client):
    payload = {
        "title": "Full card",
        "description": "some details",
        "column": "in_progress",
        "story_points": 8,
        "assignee": "Jian",
    }
    r = client.post("/api/v1/cards", json=payload)
    assert r.status_code == 201
    body = r.json()
    for key, value in payload.items():
        assert body[key] == value


def test_ticket_numbers_increment(client):
    a = client.post("/api/v1/cards", json={"title": "A"}).json()
    b = client.post("/api/v1/cards", json={"title": "B"}).json()
    c = client.post("/api/v1/cards", json={"title": "C"}).json()
    assert [a["ticket_number"], b["ticket_number"], c["ticket_number"]] == [
        "KAN-1",
        "KAN-2",
        "KAN-3",
    ]


def test_append_position_is_per_column(client):
    t0 = client.post("/api/v1/cards", json={"title": "t0", "column": "todo"}).json()
    t1 = client.post("/api/v1/cards", json={"title": "t1", "column": "todo"}).json()
    d0 = client.post("/api/v1/cards", json={"title": "d0", "column": "done"}).json()
    assert t0["position"] == 0
    assert t1["position"] == 1
    assert d0["position"] == 0  # a different column starts its own count at 0


def test_list_returns_all_created(client):
    client.post("/api/v1/cards", json={"title": "A"})
    client.post("/api/v1/cards", json={"title": "B", "column": "done"})
    cards = client.get("/api/v1/cards").json()
    assert len(cards) == 2
    assert {c["title"] for c in cards} == {"A", "B"}


def test_validation_rejects_empty_title(client):
    assert client.post("/api/v1/cards", json={"title": ""}).status_code == 422
    assert client.post("/api/v1/cards", json={"title": "   "}).status_code == 422
    assert client.post("/api/v1/cards", json={}).status_code == 422


def test_validation_story_points_must_be_fibonacci(client):
    assert client.post("/api/v1/cards", json={"title": "x", "story_points": 4}).status_code == 422
    assert client.post("/api/v1/cards", json={"title": "x", "story_points": 0}).status_code == 422
    # Allowed values and null pass.
    for pts in (1, 2, 3, 5, 8, 13, None):
        r = client.post("/api/v1/cards", json={"title": "x", "story_points": pts})
        assert r.status_code == 201


def test_validation_rejects_unknown_column(client):
    assert client.post("/api/v1/cards", json={"title": "x", "column": "backlog"}).status_code == 422


def test_ticket_number_and_position_are_not_client_settable(client):
    # Extra fields are ignored by the CardCreate schema; the server assigns them.
    r = client.post(
        "/api/v1/cards",
        json={"title": "x", "ticket_number": "KAN-999", "position": 42},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["ticket_number"] == "KAN-1"
    assert body["position"] == 0
