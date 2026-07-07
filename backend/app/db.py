"""Database wiring: synchronous SQLAlchemy 2.0 + psycopg (v3) driver (ADR 0008).

The engine reads ``DATABASE_URL`` from the environment. Locally this points at the
docker-compose Postgres; in prod it is a Fly secret pointing at Neon.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Default targets the local docker-compose Postgres. The +psycopg suffix selects
# the psycopg v3 driver for SQLAlchemy.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://kanban:kanban@localhost:5432/kanban",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency yielding a session, closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
