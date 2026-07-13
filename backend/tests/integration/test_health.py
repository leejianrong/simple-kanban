"""Health/readiness probe tests (KAN-172, observability).

Proves the acceptance criterion: ``GET /api/health`` reflects real dependency
health — it stays ``200 {"status": "ok"}`` while Postgres is reachable and flips
to a non-200 with ``status != "ok"`` when the DB is unreachable.

Per the suite convention every ``import app.*`` lives inside a test body so the
``_database`` fixture's ``DATABASE_URL`` override takes effect before the engines
are built (the PR #17 trap; see conftest ``pytest_collection_finish``).
"""
from __future__ import annotations


def test_readiness_ok_when_db_up(client):
    """Happy path: DB reachable → 200 and status ok."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_liveness_ignores_db(client):
    """Liveness is static (process up), independent of DB reachability."""
    r = client.get("/api/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readiness_unhealthy_when_db_unreachable(client):
    """DB unreachable → 503 with status != ok.

    Override ``get_db`` with a session bound to an engine pointing at a dead
    address, so the probe's ``SELECT 1`` raises and the endpoint reports
    unavailable — without disturbing the real test container.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db import get_db
    from app.main import app

    def _dead_db():
        # Port 1 refuses connections immediately → OperationalError on execute.
        bad_engine = create_engine(
            "postgresql+psycopg://kanban:kanban@localhost:1/kanban"
        )
        session = sessionmaker(bind=bad_engine)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _dead_db
    try:
        r = client.get("/api/health")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 503
    assert r.json()["status"] != "ok"
