"""Pytest fixtures for the backend API suite.

The model relies on Postgres-specific features (the ``card_ticket_seq`` sequence,
the ``'KAN-' || nextval(...)`` server default, and a CHECK constraint), so tests
run against a real Postgres — not SQLite. Rather than depend on a manually-managed
database, pytest starts an ephemeral Postgres via **testcontainers** and tears it
down at the end of the session, so the suite is fully self-contained (and CI-ready).
Requires a running Docker daemon.

Flow: start container → point DATABASE_URL at it → ``alembic upgrade head`` (which
also exercises the migrations) → reset tables + sequences between tests for
deterministic ticket numbers.
"""
from __future__ import annotations

import os

import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Start a throwaway Postgres, point the app + Alembic at it, migrate to head."""
    with PostgresContainer("postgres:17", driver="psycopg") as postgres:
        # app.db and Alembic both read DATABASE_URL at import/run time; set it
        # before any app module is imported (all app imports happen in fixtures).
        os.environ["DATABASE_URL"] = postgres.get_connection_url()
        # Auth config (M3 V6) is read at import time too. Dummy GitHub creds make
        # the OAuth routes register for the whole session (the network calls are
        # mocked in the auth tests); COOKIE_SECURE stays unset so cookies are
        # stored over the test client's http origin.
        os.environ.setdefault("GITHUB_OAUTH_CLIENT_ID", "test-client-id")
        os.environ.setdefault("GITHUB_OAUTH_CLIENT_SECRET", "test-client-secret")
        os.environ.setdefault("AUTH_SECRET", "test-secret-key-at-least-32-bytes-long!!")

        from alembic.config import Config

        from alembic import command

        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")

        yield


@pytest.fixture(autouse=True)
def _reset_tables():
    """Empty the card + epic tables and restart sequences before each test."""
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        # The auth tables (M3 V6) are cleared too so each test starts principal-free;
        # CASCADE drops dependent oauth_account/access_token rows. "user" is quoted
        # (reserved word).
        conn.execute(
            text('TRUNCATE card, epic, "user", oauth_account, access_token '
                 "RESTART IDENTITY CASCADE")
        )
        conn.execute(text("ALTER SEQUENCE card_ticket_seq RESTART WITH 1"))
        conn.execute(text("ALTER SEQUENCE epic_ticket_seq RESTART WITH 1"))
    yield


@pytest.fixture
def client():
    """A FastAPI TestClient bound to the migrated test database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
