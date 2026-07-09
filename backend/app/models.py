"""SQLAlchemy ORM models: Board, Card (a story on a board) and Epic (CONTEXT §3,
ADR 0006 + ADR 0009 + ADR 0012).

Three tables. A **board** owns a set of cards + epics (M3 V7, ADR 0012); a
**card** is a story on a board; an **epic** is a separate grouping a story can
belong to (ADR 0009). Key mechanisms:
- Each table's ``ticket_number`` is assigned atomically at INSERT from its own
  Postgres SEQUENCE via a server_default — ``'KAN-' || nextval('card_ticket_seq')``
  for cards, ``'EPIC-' || nextval('epic_ticket_seq')`` for epics — immutable, never
  reused, and independent (KAN-1 and EPIC-1 can coexist). Ticket sequences stay
  **global** across boards (D4) — no per-board prefixes.
- ``column`` is a plain ``varchar`` guarded by a CHECK constraint (not a native PG
  enum) so new column values need no ``ALTER TYPE`` migration (ADR 0008).
- Every card + epic belongs to exactly one board via a NOT NULL ``board_id`` FK
  (R2.3). ``ON DELETE CASCADE`` — deleting a board removes its cards + epics.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

VALID_COLUMNS = ("todo", "in_progress", "done")


class Board(Base):
    """A board owns a set of cards + epics (M3 V7, ADR 0012). ``owner_id`` is the
    human who owns it (nullable — the migrated default board is unclaimed until a
    user takes it; board authorization on ownership arrives in V8)."""

    __tablename__ = "board"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # FK → user.id (a UUID). ON DELETE SET NULL: deleting a user unclaims their
    # boards rather than cascading away the boards + all their cards.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Epic(Base):
    """A board-less grouping of stories (ADR 0009). No column/position/assignee/
    story_points — an epic is not a board card and is too large to estimate or
    own individually."""

    __tablename__ = "epic"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        # Assigned by the DB at INSERT; the sequence is created in the migration.
        server_default=text("'EPIC-' || nextval('epic_ticket_seq')"),
    )
    # The board this epic belongs to (M3 V7). NOT NULL; cascade on board delete.
    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("board.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CardDependency(Base):
    """A directed blocker→blocked edge between two cards on the same board
    (KAN-28, the foundation for the dependency line).

    ``blocker_id`` blocks ``blocked_id`` — i.e. the blocked card is *blocked-by*
    the blocker. Both FKs ``ON DELETE CASCADE`` so deleting a card removes any edge
    it participates in (consistent with the app's hard-delete model). A
    ``UNIQUE(blocker_id, blocked_id)`` constraint keeps an edge singular. The
    same-board rule, self-link ban and cycle prevention are enforced in the router
    (``routers/cards.py``), not the schema — they can't be a table constraint.
    """

    __tablename__ = "card_dependency"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_card_dependency_edge"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("card.id", ondelete="CASCADE"), nullable=False
    )
    blocked_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("card.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Card(Base):
    __tablename__ = "card"
    __table_args__ = (
        CheckConstraint(
            "\"column\" IN ('todo', 'in_progress', 'done')",
            name="ck_card_column",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        # Assigned by the DB at INSERT; the sequence is created in the migration.
        server_default=text("'KAN-' || nextval('card_ticket_seq')"),
    )
    # The board this story lives on (M3 V7). NOT NULL; cascade on board delete.
    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("board.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    column: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optional link to the story's parent epic. ON DELETE SET NULL so deleting an
    # epic detaches (rather than blocks or cascades) its stories — consistent with
    # the app's hard-delete model.
    epic_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("epic.id", ondelete="SET NULL"), nullable=True
    )
    story_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
