"""/api/cards endpoints (BREADBOARD §6).

Slice 1 exposes the two endpoints the walking skeleton needs:
- GET  /api/cards  — list all cards (client groups by column, sorts by position)
- POST /api/cards  — create a card (appended to the end of its column)

PATCH / DELETE / move come in later slices.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Card
from ..ordering import next_position, renumber_column
from ..schemas import CardCreate, CardMove, CardRead

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("", response_model=list[CardRead])
def list_cards(db: Session = Depends(get_db)) -> list[Card]:
    return list(
        db.scalars(select(Card).order_by(Card.column, Card.position, Card.id)).all()
    )


@router.post("", response_model=CardRead, status_code=status.HTTP_201_CREATED)
def create_card(payload: CardCreate, db: Session = Depends(get_db)) -> Card:
    card = Card(
        title=payload.title,
        description=payload.description,
        column=payload.column.value,
        position=next_position(db, payload.column.value),
        story_points=payload.story_points,
        assignee=payload.assignee,
    )
    db.add(card)
    db.commit()
    # Refresh so server-assigned fields (id, ticket_number, timestamps) are populated.
    db.refresh(card)
    return card


@router.post("/{card_id}/move", response_model=CardRead)
def move_card(
    card_id: int, payload: CardMove, db: Session = Depends(get_db)
) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Card not found"
        )

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

    # Task 2 always appends; Task 3 replaces this with a clamped insert-at-index.
    siblings.append(card)
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
