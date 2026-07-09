"""Auth-required contract + the transitional SERVICE token (M3 V8, ADR 0013).

V8 makes the whole ``/api/v1`` surface **authorization-required** — a deliberate
contract change from V4, where reads were open and writes were open unless
``API_TOKENS`` was set. Now:

- No principal (no cookie session, no valid token) → **401** on reads *and* writes.
- A valid ``API_TOKENS`` bearer → the **SERVICE** principal: full access, bypassing
  the per-board owner check (the transitional MCP/agent path, retired in V9).
- A human cookie session → owner-gated access (covered in test_authz.py).

Tokens are read from the environment per request, so ``monkeypatch.setenv`` before
a call takes effect and auto-reverts. Per the suite convention, any app-module
imports go inside test bodies.
"""
from __future__ import annotations

import pytest

# Must match conftest.SERVICE_TOKEN (the tests/integration dir isn't a package, so
# it can't be imported from conftest directly).
SERVICE_TOKEN = "svc-token-for-tests"

CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"
BOARDS = "/api/v1/boards"

AUTH = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


@pytest.fixture
def tokens_set(monkeypatch):
    """Configure valid service tokens for the duration of a test."""
    monkeypatch.setenv("API_TOKENS", f"{SERVICE_TOKEN},another-valid")


# --- unauthenticated: everything is 401 (the V8 contract change) --------------


def test_unauthenticated_reads_are_401(client, monkeypatch):
    # Reads used to be open (V4); under V8 they require a principal.
    monkeypatch.delenv("API_TOKENS", raising=False)
    assert client.get(CARDS).status_code == 401
    assert client.get(EPICS).status_code == 401
    assert client.get(BOARDS).status_code == 401


def test_unauthenticated_writes_are_401(client, monkeypatch):
    monkeypatch.delenv("API_TOKENS", raising=False)
    r = client.post(CARDS, json={"title": "no principal"})
    assert r.status_code == 401
    # RFC 7235: a 401 advertises the scheme.
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_bad_token_is_401(client, tokens_set):
    assert client.get(CARDS, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert (
        client.post(CARDS, json={"t": 1}, headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )


def test_token_ignored_when_api_tokens_unset(client, monkeypatch):
    # A bearer that isn't configured grants nothing.
    monkeypatch.delenv("API_TOKENS", raising=False)
    assert client.get(CARDS, headers=AUTH).status_code == 401


# --- SERVICE token: full access, ownership bypassed ---------------------------


def test_service_token_reads_and_writes(client, tokens_set):
    created = client.post(CARDS, json={"title": "ok"}, headers=AUTH)
    assert created.status_code == 201
    assert client.get(CARDS, headers=AUTH).status_code == 200
    assert client.get(f"{CARDS}/{created.json()['id']}", headers=AUTH).status_code == 200


def test_service_token_guards_all_mutating_card_routes(client, tokens_set):
    cid = client.post(CARDS, json={"title": "seed"}, headers=AUTH).json()["id"]

    # Every write without a principal → 401 ...
    assert client.patch(f"{CARDS}/{cid}", json={"title": "x"}).status_code == 401
    assert client.post(f"{CARDS}/{cid}/move", json={"column": "done"}).status_code == 401
    assert client.delete(f"{CARDS}/{cid}").status_code == 401

    # ... and each succeeds as the SERVICE principal.
    assert client.patch(f"{CARDS}/{cid}", json={"title": "x"}, headers=AUTH).status_code == 200
    assert (
        client.post(f"{CARDS}/{cid}/move", json={"column": "done"}, headers=AUTH).status_code == 200
    )
    assert client.delete(f"{CARDS}/{cid}", headers=AUTH).status_code == 204


def test_service_token_bypasses_board_ownership(logged_in_client, service_client):
    # A human owns a board; the SERVICE principal can still read + write it
    # (unscoped bypass — the transitional agent path).
    owned = logged_in_client.post(BOARDS, json={"name": "human-owned"}).json()["id"]
    card = service_client.post(CARDS, json={"title": "svc", "board_id": owned})
    assert card.status_code == 201
    assert service_client.get(f"{BOARDS}/{owned}").status_code == 200


def test_epic_create_is_guarded_too(client, tokens_set):
    assert client.post(EPICS, json={"name": "E"}).status_code == 401
    assert client.post(EPICS, json={"name": "E"}, headers=AUTH).status_code == 201
