"""API tests for POST /api/cards/{id}/move (move & reorder, R2)."""
from __future__ import annotations


def _create(client, title, column="todo"):
    return client.post("/api/cards", json={"title": title, "column": column}).json()


def test_move_to_another_column_appends(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "in_progress"})
    assert r.status_code == 200
    body = r.json()
    assert body["column"] == "in_progress"
    assert body["position"] == 0


def test_move_between_columns_renumbers_source(client):
    a = _create(client, "A", "todo")  # pos 0
    b = _create(client, "B", "todo")  # pos 1
    c = _create(client, "C", "todo")  # pos 2
    client.post(f"/api/cards/{a['id']}/move", json={"column": "done"})
    cards = {x["id"]: x for x in client.get("/api/cards").json()}
    assert cards[a["id"]]["column"] == "done"
    assert cards[a["id"]]["position"] == 0
    assert cards[b["id"]]["position"] == 0  # source renumbered 0..n
    assert cards[c["id"]]["position"] == 1


def test_move_into_empty_column_lands_at_zero(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "done", "position": 0})
    assert r.status_code == 200
    assert r.json()["column"] == "done"
    assert r.json()["position"] == 0


def test_move_unknown_card_returns_404(client):
    r = client.post("/api/cards/999999/move", json={"column": "done"})
    assert r.status_code == 404


def test_move_rejects_unknown_column_422(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "backlog"})
    assert r.status_code == 422


def test_move_rejects_negative_position_422(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "todo", "position": -1})
    assert r.status_code == 422
