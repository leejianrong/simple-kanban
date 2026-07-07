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
