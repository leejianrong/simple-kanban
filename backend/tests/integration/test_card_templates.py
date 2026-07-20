"""API tests for card templates + apply (M5 V19, KAN-252).

A card template is a named, board-scoped list of card payloads;
``POST /boards/{id}/templates/{tid}/apply`` instantiates them as real cards on the
board in one transaction. Covers CRUD, the apply guarantee (the template's cards end
up on the board), atomic apply on a bad epic, board-scoping (cross-board id 404), and
authz (non-member 403). Per the suite convention, any app-module imports go inside
test bodies, not at module top (the PR #17 trap)."""
from __future__ import annotations

import pytest


@pytest.fixture
def client(logged_in_client):
    """Run as the board-owning session user (owns the reset fixture's board id=1)."""
    return logged_in_client


CARDS = "/api/v1/cards"


def _templates(board_id: int) -> str:
    return f"/api/v1/boards/{board_id}/templates"


PLAN = [
    {"title": "Design", "priority": "high", "column": "todo"},
    {"title": "Build", "description": "the thing"},
    {"title": "Ship", "column": "done"},
]


def test_create_list_get_delete_template(client):
    created = client.post(_templates(1), json={"name": "sprint", "cards": PLAN})
    assert created.status_code == 201
    tpl = created.json()
    assert tpl["board_id"] == 1
    assert tpl["name"] == "sprint"
    assert [c["title"] for c in tpl["cards"]] == ["Design", "Build", "Ship"]

    listed = client.get(_templates(1))
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [tpl["id"]]

    got = client.get(f"{_templates(1)}/{tpl['id']}")
    assert got.status_code == 200

    deleted = client.delete(f"{_templates(1)}/{tpl['id']}")
    assert deleted.status_code == 204
    assert client.get(_templates(1)).json() == []


def test_create_template_rejects_empty_cards(client):
    assert client.post(_templates(1), json={"name": "x", "cards": []}).status_code == 422


def test_create_template_rejects_blank_name(client):
    assert client.post(
        _templates(1), json={"name": "  ", "cards": PLAN}
    ).status_code == 422


def test_apply_template_seeds_the_plan(client):
    tpl = client.post(_templates(1), json={"name": "sprint", "cards": PLAN}).json()
    r = client.post(f"{_templates(1)}/{tpl['id']}/apply")
    assert r.status_code == 201
    created = r.json()
    assert [c["title"] for c in created] == ["Design", "Build", "Ship"]
    # Field payloads flowed through (priority + column).
    by_title = {c["title"]: c for c in created}
    assert by_title["Design"]["priority"] == "high"
    assert by_title["Ship"]["column"] == "done"

    # The cards really exist on the board now.
    on_board = {c["title"] for c in client.get(CARDS, params={"board_id": 1}).json()}
    assert {"Design", "Build", "Ship"} <= on_board


def test_apply_is_atomic_on_a_bad_epic(client):
    # A card in the template references a non-existent epic → the whole apply 422s and
    # no cards are created (atomic, one transaction).
    bad_plan = [
        {"title": "ok"},
        {"title": "bad", "epic_id": 9_999_999},
    ]
    tpl = client.post(_templates(1), json={"name": "bad", "cards": bad_plan}).json()
    before = len(client.get(CARDS, params={"board_id": 1}).json())
    r = client.post(f"{_templates(1)}/{tpl['id']}/apply")
    assert r.status_code == 422
    after = len(client.get(CARDS, params={"board_id": 1}).json())
    assert after == before  # nothing created


def test_templates_are_board_scoped(client):
    other = client.post("/api/v1/boards", json={"name": "Other"}).json()
    t1 = client.post(_templates(1), json={"name": "on-1", "cards": PLAN}).json()
    # A template id addressed under the wrong board 404s (not reachable cross-board).
    assert client.get(f"{_templates(other['id'])}/{t1['id']}").status_code == 404
    assert client.delete(f"{_templates(other['id'])}/{t1['id']}").status_code == 404
    assert client.post(f"{_templates(other['id'])}/{t1['id']}/apply").status_code == 404


def test_get_missing_template_is_404(client):
    assert client.get(f"{_templates(1)}/9999").status_code == 404


def test_non_member_cannot_touch_templates(client, login_as):
    tpl = client.post(_templates(1), json={"name": "private", "cards": PLAN}).json()
    stranger = login_as("stranger@example.com", "gh-stranger")
    assert stranger.get(_templates(1)).status_code == 403
    assert stranger.post(_templates(1), json={"name": "n", "cards": PLAN}).status_code == 403
    assert stranger.post(f"{_templates(1)}/{tpl['id']}/apply").status_code == 403
    assert stranger.delete(f"{_templates(1)}/{tpl['id']}").status_code == 403


def test_templates_on_unknown_board_is_404(client):
    assert client.get(_templates(9999)).status_code == 404
