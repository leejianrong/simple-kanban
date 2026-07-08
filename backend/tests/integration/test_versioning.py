"""API versioning tests (Milestone 2 V2, P3 / spike-p3-versioning.md).

Each router is dual-mounted: the canonical ``/api/v1`` prefix and a temporary
``/api`` compat alias, both hitting identical handlers. These tests pin that
contract for cards and epics, and assert the alias is hidden from OpenAPI while
``/api/health`` stays unversioned. Per the suite convention, any app-module
imports go inside test bodies, not at module top.
"""
from __future__ import annotations

# --- cards: canonical path + alias ----------------------------------------


def test_cards_canonical_v1_path_works(client):
    r = client.post("/api/v1/cards", json={"title": "via v1"})
    assert r.status_code == 201
    assert r.json()["ticket_number"] == "KAN-1"

    listed = client.get("/api/v1/cards")
    assert listed.status_code == 200
    assert [c["title"] for c in listed.json()] == ["via v1"]


def test_cards_api_alias_works(client):
    r = client.post("/api/cards", json={"title": "via alias"})
    assert r.status_code == 201
    assert r.json()["ticket_number"] == "KAN-1"

    listed = client.get("/api/cards")
    assert listed.status_code == 200
    assert [c["title"] for c in listed.json()] == ["via alias"]


def test_cards_both_mounts_hit_the_same_handler(client):
    # A card created via the alias is visible through the versioned path.
    created = client.post("/api/cards", json={"title": "shared"}).json()
    fetched = client.get(f"/api/v1/cards/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "shared"


# --- epics: canonical path + alias -----------------------------------------


def test_epics_canonical_v1_path_works(client):
    r = client.post("/api/v1/epics", json={"name": "via v1"})
    assert r.status_code == 201
    assert r.json()["ticket_number"] == "EPIC-1"

    listed = client.get("/api/v1/epics")
    assert listed.status_code == 200
    assert [e["name"] for e in listed.json()] == ["via v1"]


def test_epics_api_alias_works(client):
    r = client.post("/api/epics", json={"name": "via alias"})
    assert r.status_code == 201
    assert r.json()["ticket_number"] == "EPIC-1"

    listed = client.get("/api/epics")
    assert listed.status_code == 200
    assert [e["name"] for e in listed.json()] == ["via alias"]


def test_epics_both_mounts_hit_the_same_handler(client):
    created = client.post("/api/epics", json={"name": "shared"}).json()
    fetched = client.get(f"/api/v1/epics/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "shared"


# --- schema + unversioned health -------------------------------------------


def test_openapi_shows_only_v1_paths_not_the_alias(client):
    paths = client.get("/openapi.json").json()["paths"]
    # Canonical versioned paths are documented.
    assert "/api/v1/cards" in paths
    assert "/api/v1/epics" in paths
    # The /api alias is hidden (include_in_schema=False).
    assert "/api/cards" not in paths
    assert "/api/epics" not in paths


def test_health_stays_unversioned(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
