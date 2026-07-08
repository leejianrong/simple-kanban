"""API tests for the epic/story model (Milestone 2 V1, P1 + P1-v).

Covers the `kind` default, creating epics, parenting a story to an epic, the
parent-validation rules (epic-with-parent, missing/non-epic parent, self-parent),
and PATCH re-parenting. Uses only the HTTP client — per the suite convention any
app-module imports go inside test bodies, not at module top.
"""
from __future__ import annotations


def _create(client, **fields):
    payload = {"title": "T", **fields}
    r = client.post("/api/cards", json=payload)
    return r


# --- kind on create --------------------------------------------------------


def test_kind_defaults_to_story(client):
    body = _create(client).json()
    assert body["kind"] == "story"
    assert body["parent_id"] is None


def test_create_epic(client):
    r = _create(client, title="An epic", kind="epic")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "epic"
    assert body["parent_id"] is None


def test_create_rejects_unknown_kind(client):
    assert _create(client, kind="bug").status_code == 422


# --- parenting a story -----------------------------------------------------


def test_story_with_valid_epic_parent(client):
    epic = _create(client, title="Epic", kind="epic").json()
    r = _create(client, title="Story", kind="story", parent_id=epic["id"])
    assert r.status_code == 201
    assert r.json()["parent_id"] == epic["id"]


def test_story_default_kind_can_have_epic_parent(client):
    # kind omitted → defaults to story, which may still carry a parent.
    epic = _create(client, title="Epic", kind="epic").json()
    r = _create(client, title="Child", parent_id=epic["id"])
    assert r.status_code == 201
    assert r.json()["kind"] == "story"
    assert r.json()["parent_id"] == epic["id"]


# --- parent validation (P1-v) ---------------------------------------------


def test_reject_epic_with_parent(client):
    epic = _create(client, title="Parent epic", kind="epic").json()
    r = _create(client, title="Nested epic", kind="epic", parent_id=epic["id"])
    assert r.status_code == 422


def test_reject_missing_parent(client):
    r = _create(client, title="Orphan", kind="story", parent_id=999999)
    assert r.status_code == 422


def test_reject_non_epic_parent(client):
    story = _create(client, title="A story", kind="story").json()
    r = _create(client, title="Child of a story", kind="story", parent_id=story["id"])
    assert r.status_code == 422


# --- PATCH re-parent -------------------------------------------------------


def test_patch_reparents_story(client):
    epic_a = _create(client, title="Epic A", kind="epic").json()
    epic_b = _create(client, title="Epic B", kind="epic").json()
    story = _create(client, title="Story", kind="story", parent_id=epic_a["id"]).json()

    r = client.patch(f"/api/cards/{story['id']}", json={"parent_id": epic_b["id"]})
    assert r.status_code == 200
    assert r.json()["parent_id"] == epic_b["id"]


def test_patch_can_clear_parent(client):
    epic = _create(client, title="Epic", kind="epic").json()
    story = _create(client, title="Story", kind="story", parent_id=epic["id"]).json()

    r = client.patch(f"/api/cards/{story['id']}", json={"parent_id": None})
    assert r.status_code == 200
    assert r.json()["parent_id"] is None


def test_patch_reject_reparent_to_non_epic(client):
    other = _create(client, title="Another story", kind="story").json()
    story = _create(client, title="Story", kind="story").json()
    r = client.patch(f"/api/cards/{story['id']}", json={"parent_id": other["id"]})
    assert r.status_code == 422


def test_patch_reject_self_parent(client):
    story = _create(client, title="Story", kind="story").json()
    r = client.patch(f"/api/cards/{story['id']}", json={"parent_id": story["id"]})
    assert r.status_code == 422


def test_patch_reject_parent_on_epic(client):
    parent = _create(client, title="Parent epic", kind="epic").json()
    epic = _create(client, title="Epic", kind="epic").json()
    r = client.patch(f"/api/cards/{epic['id']}", json={"parent_id": parent["id"]})
    assert r.status_code == 422


# --- delete detaches children (ON DELETE SET NULL) -------------------------


def test_deleting_epic_detaches_its_stories(client):
    epic = _create(client, title="Epic", kind="epic").json()
    story = _create(client, title="Story", kind="story", parent_id=epic["id"]).json()

    assert client.delete(f"/api/cards/{epic['id']}").status_code == 204
    # The story survives, with its parent reference cleared rather than dangling.
    body = client.get(f"/api/cards/{story['id']}").json()
    assert body["parent_id"] is None
