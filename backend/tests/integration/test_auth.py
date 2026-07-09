"""Auth-required contract for ``/api/v1`` (M3 V8, ADR 0013; V10, ADR 0015).

V8 made the whole ``/api/v1`` surface **authorization-required** — a deliberate
contract change from V4 (where reads were open and writes open unless
``API_TOKENS`` was set). **V10 retired the transitional ``API_TOKENS`` SERVICE
bypass**, so now there are exactly two ways to authenticate:

- A human **cookie session** → owner-gated access (covered in test_authz.py).
- A **personal access token** bearer → its owning user, owner-gated (test_tokens.py).

Anything else — no cookie, no valid PAT, or an arbitrary bearer — is **401** on
reads *and* writes. This file pins that unauthenticated contract; the per-user
owner-gating matrix lives in test_authz.py / test_tokens.py.

Per the suite convention, any app-module imports go inside test bodies.
"""
from __future__ import annotations

CARDS = "/api/v1/cards"
EPICS = "/api/v1/epics"
BOARDS = "/api/v1/boards"


# --- unauthenticated: everything is 401 (the V8 contract, V10 no bypass) ------


def test_unauthenticated_reads_are_401(client):
    assert client.get(CARDS).status_code == 401
    assert client.get(EPICS).status_code == 401
    assert client.get(BOARDS).status_code == 401


def test_unauthenticated_writes_are_401(client):
    r = client.post(CARDS, json={"title": "no principal"})
    assert r.status_code == 401
    # RFC 7235: a 401 advertises the scheme.
    assert r.headers.get("WWW-Authenticate") == "Bearer"
    assert client.post(EPICS, json={"name": "E"}).status_code == 401
    assert client.post(BOARDS, json={"name": "B"}).status_code == 401


def test_arbitrary_bearer_is_401(client):
    # A bearer that is neither a cookie session nor a valid PAT grants nothing —
    # there is no longer any shared-token bypass (V10).
    auth = {"Authorization": "Bearer not-a-real-token"}
    assert client.get(CARDS, headers=auth).status_code == 401
    assert client.post(CARDS, json={"title": "x"}, headers=auth).status_code == 401


def test_mutating_card_routes_are_all_guarded(client):
    # Every mutating route rejects an unauthenticated caller with 401 (the id need
    # not exist — auth is checked before the row is loaded).
    assert client.patch(f"{CARDS}/1", json={"title": "x"}).status_code == 401
    assert client.post(f"{CARDS}/1/move", json={"column": "done"}).status_code == 401
    assert client.delete(f"{CARDS}/1").status_code == 401
