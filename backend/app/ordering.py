"""Card ordering helpers (SHAPING §Backend components).

``position`` is a relative sort key **within a (board, column)** — since M3 V7 a
column's ordering is per board, so both helpers are scoped by ``board_id``.
``next_position`` appends a new card to the end of its board+column;
``renumber_column`` re-sequences a board+column to contiguous positions on
move/reorder. Both ignore soft-deleted cards (``deleted_at IS NULL``, KAN-19)
so a deleted card leaves no phantom in the ordering.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Card


def next_position(db: Session, board_id: int, column: str) -> int:
    """Return the position for a card appended to the end of ``column`` on ``board_id``."""
    count = db.scalar(
        select(func.count())
        .select_from(Card)
        .where(
            Card.board_id == board_id,
            Card.column == column,
            Card.deleted_at.is_(None),
        )
    )
    return int(count or 0)


def renumber_column(db: Session, board_id: int, column: str) -> None:
    """Re-sequence a board+column's cards to contiguous positions 0..n."""
    cards = db.scalars(
        select(Card)
        .where(
            Card.board_id == board_id,
            Card.column == column,
            Card.deleted_at.is_(None),
        )
        .order_by(Card.position, Card.id)
    ).all()
    for index, card in enumerate(cards):
        card.position = index
