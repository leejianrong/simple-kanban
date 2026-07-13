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
from sqlalchemy.orm import Session, aliased

from ..auth_models import User
from ..authz import Access, authorize_board, get_principal, visible_board_ids
from ..db import get_db
from ..models import Card, CardComment, CardDependency, CardLink, Epic
from ..ordering import next_position, renumber_column
from ..pagination import NEXT_CURSOR_HEADER, decode_cursor, encode_cursor
from ..schemas import (
    CardCreate,
    CardMove,
    CardRead,
    CardUpdate,
    ColumnEnum,
    CommentCreate,
    CommentRead,
    DependencyCreate,
    LinkCreate,
)
from .boards import resolve_board_id

router = APIRouter(prefix="/cards", tags=["cards"])


def _get_or_404(db: Session, card_id: int) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


def _blocked_predicate():
    """A correlated-``EXISTS`` SQL predicate that is true for a ``Card`` (the outer
    row) iff it is **blocked** (KAN-29): it has ≥1 blocker whose ``column`` is not
    ``done``. Expressed in SQL so the ``blocked`` list filter composes cleanly with
    the other ``WHERE`` clauses and keyset pagination (``limit``/``cursor`` stay
    accurate). This is the exact SQL twin of the Python computation in
    ``_attach_dependencies`` — keep the two definitions in step.
    """
    blocker = aliased(Card)
    return (
        select(1)
        .select_from(CardDependency)
        .join(blocker, blocker.id == CardDependency.blocker_id)
        .where(
            CardDependency.blocked_id == Card.id,
            blocker.column != ColumnEnum.done.value,
        )
        .exists()
    )


def _attach_dependencies(db: Session, cards: Sequence[Card]) -> Sequence[Card]:
    """Populate the transient ``blocked_by`` / ``blocks`` lists **and the derived
    ``blocked`` flag** on each card from the ``card_dependency`` table (KAN-28 +
    KAN-29), then return the same cards.

    One query fetches every edge touching the given cards (joined to the blocker's
    ``column``) and the grouping happens in Python, so a list of N cards costs a
    single round-trip — no per-card N+1. ``blocked_by`` = ids of cards that block
    this one (edges where it is the *blocked*); ``blocks`` = ids it blocks (edges
    where it is the *blocker*). ``blocked`` is True when ≥1 of its blockers is not
    yet ``done`` — the same rule as ``_blocked_predicate``.
    """
    ids = [c.id for c in cards]
    if not ids:
        return cards
    blocker = aliased(Card)
    rows = db.execute(
        select(
            CardDependency.blocker_id,
            CardDependency.blocked_id,
            blocker.column,
        )
        .join(blocker, blocker.id == CardDependency.blocker_id)
        .where(
            or_(
                CardDependency.blocker_id.in_(ids),
                CardDependency.blocked_id.in_(ids),
            )
        )
    ).all()
    blocked_by: dict[int, list[int]] = defaultdict(list)
    blocks: dict[int, list[int]] = defaultdict(list)
    # blocked_id -> number of its blockers not yet in ``done``.
    active_blockers: dict[int, int] = defaultdict(int)
    for blocker_id, blocked_id, blocker_column in rows:
        blocked_by[blocked_id].append(blocker_id)
        blocks[blocker_id].append(blocked_id)
        if blocker_column != ColumnEnum.done.value:
            active_blockers[blocked_id] += 1
    for card in cards:
        card.blocked_by = sorted(blocked_by.get(card.id, []))
        card.blocks = sorted(blocks.get(card.id, []))
        card.blocked = active_blockers.get(card.id, 0) > 0
    _attach_links(db, cards)
    return cards


def _attach_links(db: Session, cards: Sequence[Card]) -> None:
    """Populate the transient ``links`` list on each card from the ``card_link``
    table (KAN-32), ordered by id (creation order). One grouped query over all the
    given cards, so a list of N cards costs a single round-trip — no per-card N+1
    (mirrors ``_attach_dependencies``). Called from ``_attach_dependencies`` so every
    card-returning route carries its work-links.
    """
    ids = [c.id for c in cards]
    if not ids:
        return
    rows = db.scalars(
        select(CardLink).where(CardLink.card_id.in_(ids)).order_by(CardLink.id)
    ).all()
    by_card: dict[int, list[CardLink]] = defaultdict(list)
    for link in rows:
        by_card[link.card_id].append(link)
    for card in cards:
        card.links = by_card.get(card.id, [])


def _attach_one(db: Session, card: Card) -> Card:
    """Attach dependency arrays + work-links to a single card (thin wrapper on the
    batch helper)."""
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
    blocked: bool | None = None,
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
    "changed since" feed for polling agents); ``blocked`` (KAN-29 ready/blocked
    signal — ``blocked=true`` returns only cards with ≥1 blocker not yet ``done``;
    ``blocked=false`` returns the **actionable/ready** cards, i.e. no blockers or
    all blockers done). The ``blocked`` field is on every card in the response
    regardless of this filter. It is a SQL ``EXISTS`` predicate, so it AND-s with
    the other filters and keyset pagination stays exact.

    Pagination is keyset over ``(updated_at, id)``: pass ``limit`` to cap the
    page; when a full page is returned the next page's opaque cursor rides the
    ``X-Next-Cursor`` response header (absent on the last page). Echo it back as
    ``cursor`` for the next request. The body stays a bare ``CardRead[]`` so the
    SPA is unaffected; it re-sorts by ``position`` within each column client-side.
    """
    query = select(Card).order_by(Card.updated_at, Card.id)

    if board_id is not None:
        # Naming a board authorizes against it directly (403 if no read access).
        authorize_board(db, principal, board_id, Access.READ)
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
    if blocked is not None:
        predicate = _blocked_predicate()
        query = query.where(predicate if blocked else ~predicate)
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
    authorize_board(db, principal, board_id, Access.WRITE)
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
    authorize_board(db, principal, card.board_id, Access.READ)
    return _attach_one(db, card)


@router.patch("/{card_id}", response_model=CardRead)
def update_card(
    card_id: int,
    payload: CardUpdate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Card:
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id, Access.WRITE)
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
    authorize_board(db, principal, card.board_id, Access.WRITE)
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
    authorize_board(db, principal, card.board_id, Access.WRITE)

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
    authorize_board(db, principal, card.board_id, Access.WRITE)

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
    authorize_board(db, principal, card.board_id, Access.WRITE)
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


# --- card work-links (PR / branch / CI) (KAN-32) ---------------------------


@router.post(
    "/{card_id}/links",
    response_model=CardRead,
    status_code=status.HTTP_201_CREATED,
)
def add_link(
    card_id: int,
    payload: LinkCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Card:
    """Attach a work-link (``label`` + ``url`` — e.g. a PR URL, branch, or CI run) to
    card ``{card_id}``, closing the board↔git gap (KAN-32). Returns the card with its
    refreshed ``links`` array. **404** if the card doesn't exist; owner-gated on the
    card's board.
    """
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id, Access.WRITE)
    db.add(CardLink(card_id=card.id, label=payload.label, url=payload.url))
    db.commit()
    return _attach_one(db, card)


@router.delete("/{card_id}/links/{link_id}", response_model=CardRead)
def remove_link(
    card_id: int,
    link_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Card:
    """Detach work-link ``{link_id}`` from card ``{card_id}`` (KAN-32). **404** if no
    such link belongs to the card. Returns the card with its refreshed ``links``.
    Owner-gated on the card's board.
    """
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id, Access.WRITE)
    link = db.scalars(
        select(CardLink).where(
            CardLink.id == link_id,
            CardLink.card_id == card.id,
        )
    ).first()
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Link not found"
        )
    db.delete(link)
    db.commit()
    return _attach_one(db, card)


# --- card notes / comments (KAN-33) ----------------------------------------
#
# Human/agent-authored intentional notes (a decision, a handoff, "why this is
# blocked") — **distinct from Epic 4's SYSTEM activity log** (KAN-17..20, not yet
# built), which will record machine-generated audit events. No activity-log
# machinery here. Comments are a thread, so — unlike KAN-32's small ``links`` array
# which is inlined on every card read — they get a dedicated list endpoint rather
# than being serialized onto CardRead (a card could accumulate many).


@router.get("/{card_id}/comments", response_model=list[CommentRead])
def list_comments(
    card_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Sequence[CardComment]:
    """List a card's notes (KAN-33), oldest-first (creation order). **404** if the
    card doesn't exist; owner-gated on the card's board."""
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id, Access.READ)
    return list(
        db.scalars(
            select(CardComment)
            .where(CardComment.card_id == card.id)
            .order_by(CardComment.created_at, CardComment.id)
        ).all()
    )


@router.post(
    "/{card_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    card_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> CardComment:
    """Post a note to a card (KAN-33). ``author_id`` is the acting principal (never
    the request body). Returns the created comment. **404** if the card doesn't
    exist; owner-gated on the card's board."""
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id, Access.WRITE)
    comment = CardComment(card_id=card.id, author_id=principal.id, body=payload.body)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.delete(
    "/{card_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_comment(
    card_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Response:
    """Delete **your own** note (KAN-33). **404** if no such comment belongs to the
    card; **403** if the comment was authored by someone else (delete-own-only).
    Owner-gated on the card's board."""
    card = _get_or_404(db, card_id)
    authorize_board(db, principal, card.board_id, Access.WRITE)
    comment = db.scalars(
        select(CardComment).where(
            CardComment.id == comment_id,
            CardComment.card_id == card.id,
        )
    ).first()
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    if comment.author_id != principal.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you can only delete your own comments",
        )
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
