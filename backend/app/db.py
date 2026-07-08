"""Database wiring: synchronous SQLAlchemy 2.0 + psycopg (v3) driver (ADR 0008).

The engine reads ``DATABASE_URL`` from the environment. Locally this points at the
docker-compose Postgres; in prod it is a Fly secret pointing at Neon.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Default targets the local docker-compose Postgres. The +psycopg suffix selects
# the psycopg v3 driver for SQLAlchemy.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://kanban:kanban@localhost:5432/kanban",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Second, ASYNC engine — used ONLY by fastapi-users' human login/session/OAuth
# store (Milestone 3 V6, ADR 0011). fastapi-users' user DB is async-only, so it
# needs an AsyncSession. All board/epic/card CRUD (and the agent-token lookup)
# stay on the sync engine above — ADR 0008 is preserved for the whole app surface.
# Both engines point at the same DATABASE_URL database; psycopg v3 serves sync and
# async, so the +psycopg URL works unchanged for both.
async_engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models — board domain (models.py) and auth
    (auth_models.py) share this one metadata, so one Alembic pipeline covers both."""


def get_db():
    """FastAPI dependency yielding a sync session, closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session for the auth routes only."""
    async with AsyncSessionLocal() as session:
        yield session
