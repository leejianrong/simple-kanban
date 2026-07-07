"""/api/cards endpoints (BREADBOARD §6).

- GET    /api/cards         — list all cards (client groups by column, sorts by position)
- POST   /api/cards         — create a card (appended to the end of its column)
- GET    /api/cards/{id}    — read one card
- PATCH  /api/cards/{id}    — edit fields (title/description/story_points/assignee)
- DELETE /api/cards/{id}    — hard-delete

The move/reorder endpoint (POST /api/cards/{id}/move) arrives in the next slice.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Card
from ..ordering import next_position
from ..schemas import CardCreate, CardRead, CardUpdate

router = APIRouter(prefix="/api/cards", tags=["cards"])


def _get_or_404(db: Session, card_id: int) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


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
