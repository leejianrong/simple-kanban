"""Cards endpoints (BREADBOARD §6, P4; **owner-gated in V8, ADR 0013**).

Mounted by ``main.py`` under ``/api/v1`` (e.g. ``/api/v1/cards``):

- GET    /cards         — list/query cards (filter + keyset pagination; see list_cards)
- POST   /cards         — create a card (appended to the end of its column)
- GET    /cards/{id}    — read one card
- PATCH  /cards/{id}    — edit fields (title/description/story_points/assignee)
- DELETE /cards/{id}    — hard-delete
- POST   /cards/{id}/move — move/reorder a card (column change + reorder within column)

**Authorization (V8):** every route requires a principal (`401` otherwise) and
that the principal own the card's board (`403`); the list is scoped to the caller's
boards. See :mod:`app.authz`.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from ..authz import Principal, authorize_board, get_principal, visible_board_ids
from ..db import get_db
from ..models import Card, Epic
from ..ordering import next_position, renumber_column
from ..pagination import NEXT_CURSOR_HEADER, decode_cursor, encode_cursor
from ..schemas import CardCreate, CardMove, CardRead, CardUpdate, ColumnEnum
from .boards import resolve_board_id

router = APIRouter(prefix="/cards", tags=["cards"])


def _get_or_404(db: Session, card_id: int) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


def _validate_epic(db: Session, epic_id: int | None, board_id: int) -> None:
    """A story's ``epic_id`` (if set) must reference an existing epic (ADR 0009)
    **on the same board** as the story (M3 V8 — one board owns its epics + stories;
    no cross-board links); 422 otherwise."""
    if epic_id is None:
        return
    epic = db.get(Epic, epic_id)
    if epic is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="epic_id must reference an existing epic",
        )
    if epic.board_id != board_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="epic must belong to the same board as the story",
        )


@router.get("", response_model=list[CardRead])
def list_cards(
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    board_id: int | None = None,
    column: ColumnEnum | None = None,
    epic_id: int | None = None,
    updated_since: datetime | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = None,
) -> list[Card]:
    """List cards, optionally filtered and keyset-paginated (P4).

    **Owner-scoped (V8):** results are limited to boards the caller owns (the
    SERVICE principal sees all). A ``board_id`` naming a board you don't own is a
    ``403`` (not a silently-empty list).

    Filters (all optional, AND-ed): ``board_id`` (cards on that board — the SPA
    always sends it to scope the view; omitted → all *your* boards); ``column``;
    ``epic_id`` (stories linked to that epic); ``updated_since`` (an ISO-8601
    timestamp — cards whose ``updated_at`` is at or after it, **inclusive**, the
    "changed since" feed for polling agents).

    Pagination is keyset over ``(updated_at, id)``: pass ``limit`` to cap the
    page; when a full page is returned the next page's opaque cursor rides the
    ``X-Next-Cursor`` response header (absent on the last page). Echo it back as
    ``cursor`` for the next request. The body stays a bare ``CardRead[]`` so the
    SPA is unaffected; it re-sorts by ``position`` within each column client-side.
    """
    query = select(Card).order_by(Card.updated_at, Card.id)

    if board_id is not None:
        # Naming a board authorizes against it directly (403 if not yours).
        authorize_board(db, principal, board_id)
        query = query.where(Card.board_id == board_id)
    else:
        # No board named → scope to every board the caller may see.
        scope = visible_board_ids(principal)
        if scope is not None:
            query = query.where(Card.board_id.in_(scope))
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
def create_card(
    payload: CardCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Card:
    board_id = resolve_board_id(db, payload.board_id)
    authorize_board(db, principal, board_id)
    _validate_epic(db, payload.epic_id, board_id)
    card = Card(
        board_id=board_id,
        title=payload.title,
        description=payload.description,
        column=payload.column.value,
        position=next_position(db, board_id, payload.column.value),
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
def get_card(
    card_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Card:
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id)
    return card


@router.patch("/{card_id}", response_model=CardRead)
def update_card(
    card_id: int,
    payload: CardUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Card:
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id)
    # Only fields the client actually sent; distinguishes "omitted" from "set null".
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and (data["title"] is None or not str(data["title"]).strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="title must not be empty",
        )
    if "epic_id" in data:
        _validate_epic(db, data["epic_id"], card.board_id)
    for field, value in data.items():
        setattr(card, field, value)
    db.commit()  # updated_at is bumped server-side via onupdate
    db.refresh(card)
    return card


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    card_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Response:
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id)
    db.delete(card)
    db.commit()
    # Hard delete; the vacated position leaves an intentional gap (ADR 0006).
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{card_id}/move", response_model=CardRead)
def move_card(
    card_id: int,
    payload: CardMove,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Card:
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id)

    source_column = card.column
    target_column = payload.column.value

    # The target column's other cards **on the same board**, in order (the moved
    # card excluded). A move only reorders within a board (M3 V7).
    siblings = list(
        db.scalars(
            select(Card)
            .where(
                Card.board_id == card.board_id,
                Card.column == target_column,
                Card.id != card.id,
            )
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
        renumber_column(db, card.board_id, source_column)

    db.commit()
    db.refresh(card)
    return card
