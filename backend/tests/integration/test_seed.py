"""Tests for the demo seed data (R0.4).

The per-test fixture truncates the card table first, so each test starts from an
empty board — the same precondition the seed migration guards on.
"""
from __future__ import annotations

from collections import defaultdict

from app.db import engine
from app.seed import DEMO_CARDS, seed_demo_cards


def test_seed_inserts_demo_cards_when_empty(client):
    with engine.begin() as conn:
        inserted = seed_demo_cards(conn)
    assert inserted == len(DEMO_CARDS)

    cards = client.get("/api/cards").json()
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
    # A single pre-existing card must suppress seeding (no duplicate demo data).
    client.post("/api/cards", json={"title": "already here"})

    with engine.begin() as conn:
        inserted = seed_demo_cards(conn)

    assert inserted == 0
    assert len(client.get("/api/cards").json()) == 1
