"""Card ordering helpers (SHAPING §Backend components).

Slice 1 needs only the append-on-create rule: a new card goes to the end of its
target column (``position = current count``). The transactional ``renumber_column``
used for drag move/reorder lands in the move slice.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Card


def next_position(db: Session, column: str) -> int:
    """Return the position for a card appended to the end of ``column``."""
    count = db.scalar(
        select(func.count()).select_from(Card).where(Card.column == column)
    )
    return int(count or 0)


def renumber_column(db: Session, column: str) -> None:
    """Re-sequence a column's cards to contiguous positions 0..n."""
    cards = db.scalars(
        select(Card).where(Card.column == column).order_by(Card.position, Card.id)
    ).all()
    for index, card in enumerate(cards):
        card.position = index
