"""fastapi-users auth tables (Milestone 3 V6, ADR 0011).

fastapi-users ships its `User` / `OAuthAccount` / access-token tables as
SQLAlchemy **declarative mixins**. Mixing them into our existing ``app.db.Base``
(already a 2.0 ``DeclarativeBase``) puts them on **one shared metadata** with the
board `card`/`epic` tables — so a single Alembic pipeline autogenerates them all
(the models just need importing in ``alembic/env.py``). Spike-validated; see
`docs/milestone-3/spike-fastapi-users-sync.md`.

User ids are **UUID** (fastapi-users' ``*UUID`` mixins). These tables are read and
written **only** through the async engine (`get_async_session`); the sync engine
never touches them.
"""
from __future__ import annotations

from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from sqlalchemy.orm import Mapped, relationship

from .db import Base


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """A linked OAuth identity (e.g. a GitHub account) for a ``User``."""


class User(SQLAlchemyBaseUserTableUUID, Base):
    """The human user identity (R1.4). GitHub is the only provider wired now, but
    the model is provider-agnostic — Google/email later is registration, not a
    schema change (A3)."""

    # Eager-loaded so the user's OAuth links are available without a lazy async
    # round-trip inside fastapi-users' sync-serialized responses.
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount", lazy="joined"
    )


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    """A server-side session record for the cookie ``DatabaseStrategy`` — logout
    deletes the row, making sessions revocable (D3). Distinct from the agent
    personal-access-tokens coming in V9."""

    # The mixin defaults to "accesstoken"; use the snake_case name the docs use.
    __tablename__ = "access_token"
