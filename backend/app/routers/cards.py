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

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import Session

from ..auth_models import User
from ..authz import authorize_board, get_principal, visible_board_ids
from ..db import get_db
from ..models import Card, CardDependency, Epic
from ..ordering import next_position, renumber_column
from ..pagination import NEXT_CURSOR_HEADER, decode_cursor, encode_cursor
from ..schemas import (
    CardCreate,
    CardMove,
    CardRead,
    CardUpdate,
    ColumnEnum,
    DependencyCreate,
)
from .boards import resolve_board_id

router = APIRouter(prefix="/cards", tags=["cards"])


def _get_or_404(db: Session, card_id: int) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


def _attach_dependencies(db: Session, cards: Sequence[Card]) -> Sequence[Card]:
    """Populate the transient ``blocked_by`` / ``blocks`` lists on each card from
    the ``card_dependency`` table (KAN-28), then return the same cards.

    One query fetches every edge touching the given cards and the grouping happens
    in Python, so a list of N cards costs a single round-trip — no per-card N+1.
    ``blocked_by`` = ids of cards that block this one (edges where it is the
    *blocked*); ``blocks`` = ids it blocks (edges where it is the *blocker*).
    """
    ids = [c.id for c in cards]
    if not ids:
        return cards
    rows = db.execute(
        select(CardDependency.blocker_id, CardDependency.blocked_id).where(
            or_(
                CardDependency.blocker_id.in_(ids),
                CardDependency.blocked_id.in_(ids),
            )
        )
    ).all()
    blocked_by: dict[int, list[int]] = defaultdict(list)
    blocks: dict[int, list[int]] = defaultdict(list)
    for blocker_id, blocked_id in rows:
        blocked_by[blocked_id].append(blocker_id)
        blocks[blocker_id].append(blocked_id)
    for card in cards:
        card.blocked_by = sorted(blocked_by.get(card.id, []))
        card.blocks = sorted(blocks.get(card.id, []))
    return cards


def _attach_one(db: Session, card: Card) -> Card:
    """Attach dependency arrays to a single card (thin wrapper on the batch helper)."""
    _attach_dependencies(db, [card])
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
    principal: User = Depends(get_principal),
    board_id: int | None = None,
    column: ColumnEnum | None = None,
    epic_id: int | None = None,
    updated_since: datetime | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = None,
) -> list[Card]:
    """List cards, optionally filtered and keyset-paginated (P4).

    **Owner-scoped (V8):** results are limited to boards the caller owns. A
    ``board_id`` naming a board you don't own is a ``403`` (not a silently-empty
    list).

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
        # No board named → scope to every board the caller owns.
        query = query.where(Card.board_id.in_(visible_board_ids(principal)))
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

    _attach_dependencies(db, cards)
    return cards


@router.post("", response_model=CardRead, status_code=status.HTTP_201_CREATED)
def create_card(
    payload: CardCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
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
    return _attach_one(db, card)


@router.get("/{card_id}", response_model=CardRead)
def get_card(
    card_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Card:
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id)
    return _attach_one(db, card)


@router.patch("/{card_id}", response_model=CardRead)
def update_card(
    card_id: int,
    payload: CardUpdate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
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
    return _attach_one(db, card)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    card_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
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
    principal: User = Depends(get_principal),
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
    return _attach_one(db, card)


# --- card-to-card dependencies (KAN-28) ------------------------------------


def _blocks_reaches(db: Session, start_id: int, target_id: int) -> bool:
    """True if ``start_id`` can reach ``target_id`` by following blocks-edges
    (blocker→blocked). Iterative DFS with a visited set, so it terminates even on
    an (already-persisted) cycle.

    Used for cycle prevention: adding the edge ``blocker→blocked`` would close a
    loop iff ``blocked`` already reaches ``blocker``.
    """
    seen: set[int] = set()
    stack = [start_id]
    while stack:
        current = stack.pop()
        if current == target_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(
            db.scalars(
                select(CardDependency.blocked_id).where(
                    CardDependency.blocker_id == current
                )
            ).all()
        )
    return False


@router.post(
    "/{card_id}/dependencies",
    response_model=CardRead,
    status_code=status.HTTP_201_CREATED,
)
def add_dependency(
    card_id: int,
    payload: DependencyCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Card:
    """Record that card ``{card_id}`` is **blocked-by** card ``blocker_id`` — i.e.
    insert the edge ``(blocker_id → card_id)``. Returns the (now-blocked) card with
    refreshed ``blocked_by`` / ``blocks`` arrays.

    Guards (all 422 unless noted), mirroring ``_validate_epic``:
    - both cards must exist (**404** otherwise);
    - **same board** — the blocker must live on the blocked card's board;
    - **no self-link** — a card cannot block itself;
    - **no duplicate** — the edge must not already exist;
    - **no cycle** — the edge must not make the blocks-graph cyclic.

    Owner-gated on ``{card_id}``'s board; the same-board rule means that also covers
    the blocker.
    """
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id)

    blocker_id = payload.blocker_id
    if blocker_id == card.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="a card cannot block itself",
        )
    blocker = db.get(Card, blocker_id)
    if blocker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="blocker card not found"
        )
    if blocker.board_id != card.board_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="blocker must be on the same board",
        )
    existing = db.scalars(
        select(CardDependency).where(
            CardDependency.blocker_id == blocker_id,
            CardDependency.blocked_id == card.id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="dependency already exists",
        )
    # Adding blocker→card would create a cycle iff card already reaches blocker.
    if _blocks_reaches(db, card.id, blocker_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="dependency would create a cycle",
        )

    db.add(CardDependency(blocker_id=blocker_id, blocked_id=card.id))
    db.commit()
    return _attach_one(db, card)


@router.delete("/{card_id}/dependencies/{blocker_id}", response_model=CardRead)
def remove_dependency(
    card_id: int,
    blocker_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Card:
    """Remove the ``(blocker_id → card_id)`` edge (card ``{card_id}`` is no longer
    blocked-by ``blocker_id``). **404** if that edge doesn't exist. Returns the card
    with refreshed dependency arrays."""
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id)
    edge = db.scalars(
        select(CardDependency).where(
            CardDependency.blocker_id == blocker_id,
            CardDependency.blocked_id == card.id,
        )
    ).first()
    if edge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found"
        )
    db.delete(edge)
    db.commit()
    return _attach_one(db, card)
