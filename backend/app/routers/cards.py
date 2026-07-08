"""Cards endpoints (BREADBOARD §6, P4).

Mounted by ``main.py`` under ``/api/v1`` (e.g. ``/api/v1/cards``):

- GET    /cards         — list/query cards (filter + keyset pagination; see list_cards)
- POST   /cards         — create a card (appended to the end of its column)
- GET    /cards/{id}    — read one card
- PATCH  /cards/{id}    — edit fields (title/description/story_points/assignee)
- DELETE /cards/{id}    — hard-delete
- POST   /cards/{id}/move — move/reorder a card (column change + reorder within column)
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Card, Epic
from ..ordering import next_position, renumber_column
from ..pagination import NEXT_CURSOR_HEADER, decode_cursor, encode_cursor
from ..schemas import CardCreate, CardMove, CardRead, CardUpdate, ColumnEnum

router = APIRouter(prefix="/cards", tags=["cards"])


def _get_or_404(db: Session, card_id: int) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


def _validate_epic(db: Session, epic_id: int | None) -> None:
    """A story's ``epic_id`` (if set) must reference an existing epic (ADR 0009);
    422 otherwise."""
    if epic_id is None:
        return
    if db.get(Epic, epic_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="epic_id must reference an existing epic",
        )


@router.get("", response_model=list[CardRead])
def list_cards(
    response: Response,
    db: Session = Depends(get_db),
    column: ColumnEnum | None = None,
    epic_id: int | None = None,
    updated_since: datetime | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = None,
) -> list[Card]:
    """List cards, optionally filtered and keyset-paginated (P4).

    Filters (all optional, AND-ed): ``column``; ``epic_id`` (stories linked to
    that epic); ``updated_since`` (an ISO-8601 timestamp — cards whose
    ``updated_at`` is at or after it, **inclusive**, the "changed since" feed for
    polling agents). With no params the response is the full list, unchanged.

    Pagination is keyset over ``(updated_at, id)``: pass ``limit`` to cap the
    page; when a full page is returned the next page's opaque cursor rides the
    ``X-Next-Cursor`` response header (absent on the last page). Echo it back as
    ``cursor`` for the next request. The body stays a bare ``CardRead[]`` so the
    SPA is unaffected; it re-sorts by ``position`` within each column client-side.

    Requesting unassigned stories (``epic_id IS NULL``) is intentionally out of
    scope for V3 — add it here if a client needs it.
    """
    query = select(Card).order_by(Card.updated_at, Card.id)

    if column is not None:
        query = query.where(Card.column == column.value)
    if epic_id is not None:
        query = query.where(Card.epic_id == epic_id)
    if updated_since is not None:
        query = query.where(Card.updated_at >= updated_since)
    if cursor is not None:
        try:
            cursor_updated_at, cursor_id = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid cursor",
            ) from exc
        query = query.where(
            tuple_(Card.updated_at, Card.id) > (cursor_updated_at, cursor_id)
        )
    if limit is not None:
        query = query.limit(limit)

    cards = list(db.scalars(query).all())

    # A full page implies there may be more — hand back the next cursor. A short
    # (or empty) page is the last one, so no header.
    if limit is not None and len(cards) == limit:
        last = cards[-1]
        response.headers[NEXT_CURSOR_HEADER] = encode_cursor(last.updated_at, last.id)

    return cards


@router.post("", response_model=CardRead, status_code=status.HTTP_201_CREATED)
def create_card(payload: CardCreate, db: Session = Depends(get_db)) -> Card:
    _validate_epic(db, payload.epic_id)
    card = Card(
        title=payload.title,
        description=payload.description,
        column=payload.column.value,
        position=next_position(db, payload.column.value),
        story_points=payload.story_points,
        assignee=payload.assignee,
        epic_id=payload.epic_id,
    )
    db.add(card)
    db.commit()
    # Refresh so server-assigned fields (id, ticket_number, timestamps) are populated.
    db.refresh(card)
    return card


@router.get("/{card_id}", response_model=CardRead)
def get_card(card_id: int, db: Session = Depends(get_db)) -> Card:
    return _get_or_404(db, card_id)


@router.patch("/{card_id}", response_model=CardRead)
def update_card(
    card_id: int, payload: CardUpdate, db: Session = Depends(get_db)
) -> Card:
    card = _get_or_404(db, card_id)
    # Only fields the client actually sent; distinguishes "omitted" from "set null".
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and (data["title"] is None or not str(data["title"]).strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="title must not be empty",
        )
    if "epic_id" in data:
        _validate_epic(db, data["epic_id"])
    for field, value in data.items():
        setattr(card, field, value)
    db.commit()  # updated_at is bumped server-side via onupdate
    db.refresh(card)
    return card


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: int, db: Session = Depends(get_db)) -> Response:
    card = _get_or_404(db, card_id)
    db.delete(card)
    db.commit()
    # Hard delete; the vacated position leaves an intentional gap (ADR 0006).
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{card_id}/move", response_model=CardRead)
def move_card(
    card_id: int, payload: CardMove, db: Session = Depends(get_db)
) -> Card:
    card = _get_or_404(db, card_id)

    source_column = card.column
    target_column = payload.column.value

    # The target column's other cards, in order (the moved card excluded).
    siblings = list(
        db.scalars(
            select(Card)
            .where(Card.column == target_column, Card.id != card.id)
            .order_by(Card.position, Card.id)
        ).all()
    )

    # Insert at the requested index (clamped); None => append to the end.
    index = payload.position if payload.position is not None else len(siblings)
    index = max(0, min(index, len(siblings)))
    siblings.insert(index, card)
    card.column = target_column
    for pos, sibling in enumerate(siblings):
        sibling.position = pos

    # Flush so the moved card's new column is visible to the source renumber query
    # (the session has autoflush disabled).
    db.flush()
    if source_column != target_column:
        renumber_column(db, source_column)

    db.commit()
    db.refresh(card)
    return card
