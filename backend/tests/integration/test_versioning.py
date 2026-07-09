"""API versioning tests (Milestone 2 V2, P3 / spike-p3-versioning.md).

Each router is mounted under the canonical ``/api/v1`` prefix. The temporary
``/api`` compat alias that eased the V2 migration has since been dropped (all
clients ride ``/api/v1``), so these tests pin the versioned contract for cards
and epics, assert the unversioned alias is gone from the schema, and confirm
``/api/health`` stays unversioned. Per the suite convention, any app-module
imports go inside test bodies, not at module top.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so these board tests run as the
    board-owning session user, shadowing conftest's unauthenticated ``client``.
    Claim-on-login makes this user own the reset fixture's default board."""
    return logged_in_client

# --- cards: canonical versioned path --------------------------------------


def test_cards_canonical_v1_path_works(client):
    r = client.post("/api/v1/cards", json={"title": "via v1"})
    assert r.status_code == 201
    assert r.json()["ticket_number"] == "KAN-1"

    listed = client.get("/api/v1/cards")
    assert listed.status_code == 200
    assert [c["title"] for c in listed.json()] == ["via v1"]


# --- epics: canonical versioned path --------------------------------------


def test_epics_canonical_v1_path_works(client):
    r = client.post("/api/v1/epics", json={"name": "via v1"})
    assert r.status_code == 201
    assert r.json()["ticket_number"] == "EPIC-1"

    listed = client.get("/api/v1/epics")
    assert listed.status_code == 200
    assert [e["name"] for e in listed.json()] == ["via v1"]


# --- schema + unversioned health -------------------------------------------


def test_openapi_serves_v1_and_not_the_dropped_alias(client):
    paths = client.get("/openapi.json").json()["paths"]
    # Canonical versioned paths are documented.
    assert "/api/v1/cards" in paths
    assert "/api/v1/epics" in paths
    # The former /api alias is gone — no unversioned card/epic routes exist.
    assert "/api/cards" not in paths
    assert "/api/epics" not in paths


def test_health_stays_unversioned(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
