"""Cards endpoints (BREADBOARD §6).

Mounted by ``main.py`` under ``/api/v1`` (canonical) and ``/api`` (compat alias),
so the paths below are relative to those prefixes (e.g. ``/api/v1/cards``):

- GET    /cards         — list all cards (client groups by column, sorts by position)
- POST   /cards         — create a card (appended to the end of its column)
- GET    /cards/{id}    — read one card
- PATCH  /cards/{id}    — edit fields (title/description/story_points/assignee)
- DELETE /cards/{id}    — hard-delete
- POST   /cards/{id}/move — move/reorder a card (column change + reorder within column)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Card, Epic
from ..ordering import next_position, renumber_column
from ..schemas import CardCreate, CardMove, CardRead, CardUpdate

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
def list_cards(db: Session = Depends(get_db)) -> list[Card]:
    return list(
        db.scalars(select(Card).order_by(Card.column, Card.position, Card.id)).all()
    )


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
