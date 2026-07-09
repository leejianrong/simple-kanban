"""Tests for the demo seed data (R0.4).

The per-test fixture truncates the card table first, so each test starts from an
empty board — the same precondition the seed migration guards on.

Note: app modules (app.db / app.seed) are imported *inside* the tests, not at
module top. The session fixture sets DATABASE_URL to the throwaway testcontainer
before any app import; importing app.db at collection time would bind its engine
to the default URL and break the whole suite.
"""
from __future__ import annotations

from collections import defaultdict

import pytest


@pytest.fixture
def client(logged_in_client):
    """V8 (ADR 0013): /api/v1 is owner-gated, so these board tests run as the
    board-owning session user, shadowing conftest's unauthenticated ``client``.
    Claim-on-login makes this user own the reset fixture's default board."""
    return logged_in_client


def test_seed_inserts_demo_cards_when_empty(client):
    from app.db import engine
    from app.seed import DEMO_CARDS, seed_demo_cards

    with engine.begin() as conn:
        inserted = seed_demo_cards(conn)
    assert inserted == len(DEMO_CARDS)

    cards = client.get("/api/v1/cards").json()
    assert len(cards) == len(DEMO_CARDS)

    # Ticket numbers were assigned by the sequence, not hard-coded in the seed.
    assert all(c["ticket_number"].startswith("KAN-") for c in cards)

    # Cards span all three columns and each column is contiguous from 0.
    by_column: dict[str, list[int]] = defaultdict(list)
    for c in cards:
        by_column[c["column"]].append(c["position"])
    assert set(by_column) == {"todo", "in_progress", "done"}
    for positions in by_column.values():
        assert sorted(positions) == list(range(len(positions)))


def test_seed_is_a_noop_when_board_not_empty(client):
    from app.db import engine
    from app.seed import seed_demo_cards

    # A single pre-existing card must suppress seeding (no duplicate demo data).
    client.post("/api/v1/cards", json={"title": "already here"})

    with engine.begin() as conn:
        inserted = seed_demo_cards(conn)

    assert inserted == 0
    assert len(client.get("/api/v1/cards").json()) == 1
