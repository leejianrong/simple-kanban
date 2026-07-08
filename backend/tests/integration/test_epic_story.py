"""API tests for the epic entity + story→epic links (Milestone 2 V1, ADR 0009).

Covers epic CRUD, the independent EPIC-<n> ticket sequence, linking a story to an
epic (create + PATCH), epic-link validation, and detach-on-delete. Uses only the
HTTP client — per the suite convention any app-module imports go inside test
bodies, not at module top.
"""
from __future__ import annotations


def _create_card(client, **fields):
    return client.post("/api/cards", json={"title": "T", **fields})


def _create_epic(client, **fields):
    return client.post("/api/epics", json={"name": "E", **fields})


# --- epic CRUD -------------------------------------------------------------


def test_create_epic_gets_epic_ticket(client):
    r = _create_epic(client, name="Mobile Checkout", description="Pay on mobile")
    assert r.status_code == 201
    body = r.json()
    assert body["ticket_number"] == "EPIC-1"
    assert body["name"] == "Mobile Checkout"
    assert body["description"] == "Pay on mobile"
    # An epic is not a board card — no column/position/assignee/story_points.
    assert "column" not in body
    assert "position" not in body
    assert "story_points" not in body
    assert "assignee" not in body


def test_epic_ticket_sequence_is_independent_of_cards(client):
    card = _create_card(client).json()
    epic = _create_epic(client).json()
    # Cards and epics number from separate sequences.
    assert card["ticket_number"] == "KAN-1"
    assert epic["ticket_number"] == "EPIC-1"


def test_epic_ticket_numbers_increment(client):
    a = _create_epic(client, name="A").json()
    b = _create_epic(client, name="B").json()
    assert [a["ticket_number"], b["ticket_number"]] == ["EPIC-1", "EPIC-2"]


def test_epic_create_rejects_empty_name(client):
    assert client.post("/api/epics", json={"name": ""}).status_code == 422
    assert client.post("/api/epics", json={"name": "   "}).status_code == 422
    assert client.post("/api/epics", json={}).status_code == 422


def test_list_and_get_epics(client):
    _create_epic(client, name="A")
    _create_epic(client, name="B")
    listed = client.get("/api/epics").json()
    assert {e["name"] for e in listed} == {"A", "B"}
    one = listed[0]
    assert client.get(f"/api/epics/{one['id']}").json() == one


def test_get_missing_epic_404(client):
    assert client.get("/api/epics/999").status_code == 404


def test_patch_epic_fields(client):
    epic = _create_epic(client, name="Before").json()
    r = client.patch(f"/api/epics/{epic['id']}", json={"name": "After", "description": "d"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "After"
    assert body["description"] == "d"


def test_patch_epic_rejects_empty_name(client):
    epic = _create_epic(client).json()
    assert client.patch(f"/api/epics/{epic['id']}", json={"name": ""}).status_code == 422


def test_delete_epic(client):
    epic = _create_epic(client).json()
    assert client.delete(f"/api/epics/{epic['id']}").status_code == 204
    assert client.get(f"/api/epics/{epic['id']}").status_code == 404


# --- linking a story to an epic --------------------------------------------


def test_card_has_no_epic_by_default(client):
    assert _create_card(client).json()["epic_id"] is None


def test_create_card_with_valid_epic(client):
    epic = _create_epic(client).json()
    r = _create_card(client, epic_id=epic["id"])
    assert r.status_code == 201
    assert r.json()["epic_id"] == epic["id"]


def test_create_card_rejects_missing_epic(client):
    assert _create_card(client, epic_id=999999).status_code == 422


def test_patch_relinks_story_to_epic(client):
    epic_a = _create_epic(client, name="A").json()
    epic_b = _create_epic(client, name="B").json()
    card = _create_card(client, epic_id=epic_a["id"]).json()

    r = client.patch(f"/api/cards/{card['id']}", json={"epic_id": epic_b["id"]})
    assert r.status_code == 200
    assert r.json()["epic_id"] == epic_b["id"]


def test_patch_can_clear_epic_link(client):
    epic = _create_epic(client).json()
    card = _create_card(client, epic_id=epic["id"]).json()
    r = client.patch(f"/api/cards/{card['id']}", json={"epic_id": None})
    assert r.status_code == 200
    assert r.json()["epic_id"] is None


def test_patch_rejects_missing_epic(client):
    card = _create_card(client).json()
    assert client.patch(f"/api/cards/{card['id']}", json={"epic_id": 999999}).status_code == 422


# --- delete detaches child stories (ON DELETE SET NULL) --------------------


def test_deleting_epic_detaches_its_stories(client):
    epic = _create_epic(client).json()
    card = _create_card(client, epic_id=epic["id"]).json()

    assert client.delete(f"/api/epics/{epic['id']}").status_code == 204
    # The story survives on the board, with its epic link cleared.
    body = client.get(f"/api/cards/{card['id']}").json()
    assert body["epic_id"] is None
