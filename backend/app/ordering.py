"""Card ordering helpers (SHAPING §Backend components).

``position`` is a relative sort key **within a (board, column)** — since M3 V7 a
column's ordering is per board, so both helpers are scoped by ``board_id``.
``next_position`` appends a new card to the end of its board+column;
``renumber_column`` re-sequences a board+column to contiguous positions on
move/reorder. Both ignore soft-deleted cards (``deleted_at IS NULL``, KAN-19)
so a deleted card leaves no phantom in the ordering.

This module also owns the **dispatch selection** (M5 V12, KAN-245): picking the
next ready-to-work card on a board — the shared query behind both ``dispatch``
(claim) and ``next`` (peek) in ``routers/boards.py``.
"""
from __future__ import annotations

from sqlalchemy import Case, case, func, select
from sqlalchemy.orm import Session

from .models import Card, CardLabel
from .schemas import ColumnEnum, PriorityEnum

# Priority → sort rank (M5 V12, KAN-245). Higher rank = dispatched first, so an
# ``urgent`` card outranks a ``low`` one regardless of position. Kept as a plain
# dict so the ordering is a pure, unit-testable function (``priority_rank``) and
# the SQL ``CASE`` (``priority_rank_case``) is built from the same single source
# of truth — no drift between the Python and SQL notions of "which comes first".
PRIORITY_RANK: dict[str, int] = {
    PriorityEnum.none.value: 0,
    PriorityEnum.low.value: 1,
    PriorityEnum.medium.value: 2,
    PriorityEnum.high.value: 3,
    PriorityEnum.urgent.value: 4,
}


def priority_rank(priority: str) -> int:
    """The sort rank for a ``priority`` value (higher = more urgent). An unknown
    value ranks as ``0`` (same as ``none``), so a bad row never jumps the queue."""
    return PRIORITY_RANK.get(priority, 0)


def priority_rank_case() -> Case:
    """The SQL twin of :func:`priority_rank`: a ``CASE`` mapping ``card.priority``
    to its integer rank, for use in ``ORDER BY``. Built from ``PRIORITY_RANK`` so
    it stays in step with the Python ranking."""
    return case(PRIORITY_RANK, value=Card.priority, else_=0)


def select_next_ready_card(
    db: Session,
    board_id: int,
    *,
    label: int | None = None,
    min_priority: str | None = None,
    for_update: bool = False,
) -> Card | None:
    """Select the next ready-to-dispatch card on ``board_id`` (M5 V12, KAN-245).

    "Ready" = a live card in the ``todo`` column that is **not blocked** by an open
    dependency (a blocker not yet ``done`` and not soft-deleted). Ordered
    ``priority DESC`` (urgent → none, via :func:`priority_rank_case`) then
    ``position ASC``, and capped to one row. Returns the card, or ``None`` when the
    board has nothing ready.

    ``for_update`` adds ``FOR UPDATE SKIP LOCKED`` — the **fleet-safety** primitive
    (a DB row lock, not app-level locking; consistent with ADR 0007's LWW /
    no-realtime stance): two concurrent dispatchers each lock-and-skip, so they can
    never both claim the same row. Used by ``dispatch`` (which mutates in the same
    transaction that holds the lock); ``next`` peeks with ``for_update=False``.

    Optional selection filters (AND-ed): ``label`` (a label id — only cards carrying
    it) and ``min_priority`` (a priority value — only cards at that rank or above).
    """
    # Imported lazily to avoid a circular import: ``routers/cards.py`` imports this
    # module for the ordering helpers, so it can't be imported at module top. The
    # blocked predicate is reused (not duplicated) so "ready" here is exactly the
    # ``blocked=false`` set there.
    from .routers.cards import _blocked_predicate

    query = (
        select(Card)
        .where(
            Card.board_id == board_id,
            Card.column == ColumnEnum.todo.value,
            Card.deleted_at.is_(None),
            ~_blocked_predicate(),
        )
        .order_by(priority_rank_case().desc(), Card.position.asc())
        .limit(1)
    )
    if label is not None:
        # Cards carrying the given label (mirrors the ``label`` filter in
        # ``routers/cards.py`` so the two notions stay consistent).
        query = query.where(
            Card.id.in_(select(CardLabel.card_id).where(CardLabel.label_id == label))
        )
    if min_priority is not None:
        query = query.where(priority_rank_case() >= priority_rank(min_priority))
    if for_update:
        # SKIP LOCKED: skip rows another in-flight dispatch already locked, rather
        # than blocking on them — the fleet-safe claim (KAN-245).
        query = query.with_for_update(skip_locked=True)
    return db.scalars(query).first()


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
