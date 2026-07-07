"""/api/cards endpoints (BREADBOARD §6).

Slice 1 exposes the two endpoints the walking skeleton needs:
- GET  /api/cards  — list all cards (client groups by column, sorts by position)
- POST /api/cards  — create a card (appended to the end of its column)

PATCH / DELETE / move come in later slices.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Card
from ..ordering import next_position
from ..schemas import CardCreate, CardRead

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
