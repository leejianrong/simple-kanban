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
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        # app.db and Alembic both read DATABASE_URL at import/run time; set it
        # before any app module is imported (all app imports happen in fixtures).
        os.environ["DATABASE_URL"] = postgres.get_connection_url()

        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")

        yield


@pytest.fixture(autouse=True)
def _reset_tables():
    """Empty the card table and restart sequences before each test."""
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE card RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE card_ticket_seq RESTART WITH 1"))
    yield


@pytest.fixture
def client():
    """A FastAPI TestClient bound to the migrated test database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
