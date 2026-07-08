"""SQLAlchemy ORM models: Card (a story on the board) and Epic (CONTEXT §3, ADR
0006 + ADR 0009).

Two tables. A **card** is a story on the kanban board; an **epic** is a separate,
board-less grouping a story can belong to (ADR 0009). Key mechanisms:
- Each table's ``ticket_number`` is assigned atomically at INSERT from its own
  Postgres SEQUENCE via a server_default — ``'KAN-' || nextval('card_ticket_seq')``
  for cards, ``'EPIC-' || nextval('epic_ticket_seq')`` for epics — immutable, never
  reused, and independent (KAN-1 and EPIC-1 can coexist).
- ``column`` is a plain ``varchar`` guarded by a CHECK constraint (not a native PG
  enum) so new column values need no ``ALTER TYPE`` migration (ADR 0008).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

VALID_COLUMNS = ("todo", "in_progress", "done")


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
