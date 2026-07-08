"""API tests for optional bearer-token auth on writes (Milestone 2 V4, P2 / R3.1).

When ``API_TOKENS`` is set, mutating routes require a valid ``Authorization:
Bearer <token>``; reads stay open. When it is unset, writes are open (that
default path is exercised by the rest of the suite, which sends no token — plus
one explicit test here). Tokens are read from the environment per request, so
``monkeypatch.setenv`` before a call takes effect and auto-reverts after.

Per the suite convention, any app-module imports go inside test bodies.
"""
from __future__ import annotations

import pytest

CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"

TOKEN = "s3cret-agent-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def tokens_set(monkeypatch):
    """Configure a single valid token for the duration of a test."""
    monkeypatch.setenv("API_TOKENS", f"{TOKEN},another-valid")


# --- auth enabled: writes require a valid token -----------------------------


def test_create_without_token_is_401(client, tokens_set):
    r = client.post(CARDS, json={"title": "no token"})
    assert r.status_code == 401
    # RFC 7235: a 401 advertises the scheme.
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_create_with_bad_token_is_401(client, tokens_set):
    r = client.post(CARDS, json={"title": "bad"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_create_with_valid_token_is_201(client, tokens_set):
    r = client.post(CARDS, json={"title": "ok"}, headers=AUTH)
    assert r.status_code == 201
    assert r.json()["title"] == "ok"


def test_epic_create_is_guarded_too(client, tokens_set):
    assert client.post(EPICS, json={"name": "E"}).status_code == 401
    assert client.post(EPICS, json={"name": "E"}, headers=AUTH).status_code == 201


def test_all_mutating_card_routes_are_guarded(client, tokens_set):
    # Seed a card using a valid token so we have something to mutate.
    card = client.post(CARDS, json={"title": "seed"}, headers=AUTH).json()
    cid = card["id"]

    # Every write without a token → 401 ...
    assert client.patch(f"{CARDS}/{cid}", json={"title": "x"}).status_code == 401
    assert client.post(f"{CARDS}/{cid}/move", json={"column": "done"}).status_code == 401
    assert client.delete(f"{CARDS}/{cid}").status_code == 401

    # ... and each succeeds with a valid token.
    assert client.patch(f"{CARDS}/{cid}", json={"title": "x"}, headers=AUTH).status_code == 200
    assert (
        client.post(f"{CARDS}/{cid}/move", json={"column": "done"}, headers=AUTH).status_code
        == 200
    )
    assert client.delete(f"{CARDS}/{cid}", headers=AUTH).status_code == 204


def test_reads_stay_open_when_auth_enabled(client, tokens_set):
    # A card created with a token is then readable with no token.
    created = client.post(CARDS, json={"title": "readable"}, headers=AUTH).json()
    assert client.get(CARDS).status_code == 200
    assert client.get(f"{CARDS}/{created['id']}").status_code == 200
    assert client.get(EPICS).status_code == 200


# --- auth disabled (default): writes open -----------------------------------


def test_writes_open_when_api_tokens_unset(client, monkeypatch):
    # Be explicit that nothing is configured, regardless of ambient env.
    monkeypatch.delenv("API_TOKENS", raising=False)
    assert client.post(CARDS, json={"title": "open"}).status_code == 201
    assert client.post(EPICS, json={"name": "open-epic"}).status_code == 201
