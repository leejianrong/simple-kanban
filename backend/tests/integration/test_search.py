"""API tests for full-text card search (Milestone 5 V15, KAN-248).

Covers the ``q=`` query param on ``GET /api/v1/cards``: matching a term in the
title and in the description, relevance ranking (a title hit outranks a
description-only hit), board-access scoping (you can't search into a board you
don't own), the empty/absent ``q`` no-op, combining ``q`` with another filter, and
the ``q`` + cursor incompatibility. Per the suite convention, all app-module
imports go inside test bodies (there are none needed here).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(logged_in_client):
    """/api/v1 is owner-gated (V8), so run as the board-owning session user, which
    claims the reset fixture's default board (id=1)."""
    return logged_in_client


CARDS = "/api/v1/cards"


def _create(client, **fields):
    r = client.post(CARDS, json={"title": "T", **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _titles(response):
    return [c["title"] for c in response.json()]


# --- matching --------------------------------------------------------------


def test_q_matches_a_term_in_the_title(client):
    _create(client, title="Fix the login flow")
    _create(client, title="Refactor the dashboard")
    r = client.get(CARDS, params={"q": "login"})
    assert r.status_code == 200
    assert _titles(r) == ["Fix the login flow"]


def test_q_matches_a_term_in_the_description(client):
    _create(client, title="Card A", description="handle the OAuth callback")
    _create(client, title="Card B", description="unrelated body")
    r = client.get(CARDS, params={"q": "oauth"})
    assert r.status_code == 200
    assert _titles(r) == ["Card A"]


def test_q_is_stemmed_and_case_insensitive(client):
    # 'english' config stems (searching → search) and folds case.
    _create(client, title="Searching for bugs")
    r = client.get(CARDS, params={"q": "SEARCH"})
    assert _titles(r) == ["Searching for bugs"]


# --- ranking ---------------------------------------------------------------


def test_title_hit_ranks_above_description_only_hit(client):
    # Both cards mention "widget"; the title hit (weight A) must outrank the
    # description-only hit (weight B).
    _create(client, title="Notes", description="the widget is here")
    _create(client, title="Widget overhaul", description="unrelated")
    r = client.get(CARDS, params={"q": "widget"})
    assert r.status_code == 200
    assert _titles(r) == ["Widget overhaul", "Notes"]


# --- no-op / back-compat ---------------------------------------------------


def test_empty_q_returns_the_unfiltered_set(client):
    _create(client, title="Alpha")
    _create(client, title="Beta")
    r = client.get(CARDS, params={"q": ""})
    assert r.status_code == 200
    assert set(_titles(r)) == {"Alpha", "Beta"}


def test_whitespace_q_is_a_no_op(client):
    _create(client, title="Alpha")
    _create(client, title="Beta")
    r = client.get(CARDS, params={"q": "   "})
    assert set(_titles(r)) == {"Alpha", "Beta"}


def test_no_match_returns_empty(client):
    _create(client, title="Alpha")
    r = client.get(CARDS, params={"q": "nonexistentterm"})
    assert r.status_code == 200
    assert r.json() == []


# --- combining with other filters ------------------------------------------


def test_q_combines_with_priority_filter(client):
    _create(client, title="urgent login bug", priority="urgent")
    _create(client, title="minor login typo", priority="low")
    r = client.get(CARDS, params={"q": "login", "priority": "urgent"})
    assert _titles(r) == ["urgent login bug"]


def test_q_combines_with_column_filter(client):
    _create(client, title="deploy pipeline", column="todo")
    _create(client, title="deploy hotfix", column="done")
    r = client.get(CARDS, params={"q": "deploy", "column": "done"})
    assert _titles(r) == ["deploy hotfix"]


# --- authz -----------------------------------------------------------------


def test_q_does_not_search_into_another_users_board(client, login_as):
    # `client` (the fixture user) owns board 1. A second user owns their own board
    # with a matching card; searching (no board_id → own boards only) must not reach
    # it, and naming that board is a 403.
    stranger = login_as("stranger@example.com", "gh-stranger")
    board = stranger.post("/api/v1/boards", json={"name": "Stranger board"}).json()
    stranger.post(
        CARDS, json={"title": "secret unicorn plan", "board_id": board["id"]}
    )
    # The owner of board 1 searches the shared term and finds nothing of the stranger's.
    r = client.get(CARDS, params={"q": "unicorn"})
    assert r.status_code == 200
    assert r.json() == []
    # Naming the stranger's board directly is forbidden.
    denied = client.get(CARDS, params={"q": "unicorn", "board_id": board["id"]})
    assert denied.status_code == 403


# --- pagination interaction ------------------------------------------------


def test_q_with_cursor_is_422(client):
    r = client.get(CARDS, params={"q": "anything", "cursor": "whatever"})
    assert r.status_code == 422


def test_explicit_sort_overrides_q_ranking(client):
    # With an explicit sort, the title-weight ranking yields to the sort order.
    _create(client, title="zzz widget", description="x")
    _create(client, title="aaa widget thing widget", description="x")
    r = client.get(CARDS, params={"q": "widget", "sort": "title"})
    assert r.status_code == 200
    # Alphabetical by title (sort wins), not by ts_rank.
    assert _titles(r) == ["aaa widget thing widget", "zzz widget"]
