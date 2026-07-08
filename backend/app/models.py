"""SQLAlchemy ORM model for a Card (CONTEXT §3, ADR 0006).

One table, no other entities. Key mechanisms:
- ``ticket_number`` is assigned atomically at INSERT from a Postgres SEQUENCE via a
  server_default of ``'KAN-' || nextval('card_ticket_seq')`` — immutable, never reused.
- ``column`` is a plain ``varchar`` guarded by a CHECK constraint (not a native PG enum)
  so new column values need no ``ALTER TYPE`` migration (ADR 0008).
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
# A card is either an epic (a parent grouping) or a story (may belong to an epic).
# Like `column`, `kind` is a plain varchar guarded by a CHECK constraint rather than
# a native PG enum, so adding a kind later needs no ALTER TYPE migration (ADR 0008).
VALID_KINDS = ("epic", "story")


class Card(Base):
    __tablename__ = "card"
    __table_args__ = (
        CheckConstraint(
            "\"column\" IN ('todo', 'in_progress', 'done')",
            name="ck_card_column",
        ),
        CheckConstraint(
            "kind IN ('epic', 'story')",
            name="ck_card_kind",
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
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'story'")
    )
    # Self-FK: a story may point at its parent epic. ON DELETE SET NULL so deleting
    # an epic detaches (rather than blocks or cascades) its stories — consistent
    # with the app's hard-delete model.
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("card.id", ondelete="SET NULL"), nullable=True
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
