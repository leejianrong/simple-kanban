"""Boards endpoints (M3 V7, ADR 0012; **owner-gated in V8, ADR 0013**).

A board is a first-class entity owning a set of cards + epics. Full CRUD, mirroring
the flat structure of the cards/epics routers (API-first, ADR 0005). Mounted by
``main.py`` under ``/api/v1`` (e.g. ``/api/v1/boards``):

- GET    /boards       — list the caller's boards
- POST   /boards       — create a board (owner = the calling user)
- GET    /boards/{id}  — read one board (viewer or above)
- PATCH  /boards/{id}  — rename (owner only)
- DELETE /boards/{id}  — hard-delete; its cards + epics cascade away (owner only)
- GET    /boards/{id}/activity — the board's activity feed (viewer or above; KAN-18)

**Authorization (V8 + KAN-13, ADR 0013):** every route requires a principal (`401`
otherwise). Reads are ``Access.READ`` (viewer or above); rename/delete are
``Access.MANAGE`` (owner only). The list stays owner-scoped (member visibility is
KAN-15). See :mod:`app.authz`.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from ..activity import record_activity
from ..auth_models import User
from ..authz import Access, authorize_board, get_principal, visible_board_ids
from ..db import get_db
from ..metrics import compute_metrics, parse_move_target
from ..models import Activity, Board, BoardMember, Card
from ..ordering import next_position, renumber_column, select_next_ready_card
from ..pagination import NEXT_CURSOR_HEADER, decode_cursor, encode_cursor
from ..schemas import (
    ActivityRead,
    BoardCreate,
    BoardMetricsRead,
    BoardRead,
    BoardUpdate,
    CardRead,
    ColumnEnum,
    DispatchRequest,
    PriorityEnum,
)

router = APIRouter(prefix="/boards", tags=["boards"])


def resolve_board_id(db: Session, board_id: int | None) -> int:
    """Resolve the target board for a card/epic write.

    ``None`` → the default board (the earliest one), so pre-board clients keep
    working. A supplied id must reference an existing board (422). 409 if no board
    exists at all to default to. (Ownership of the resolved board is enforced
    separately by the caller via :func:`app.authz.authorize_board`.)
    """
    if board_id is None:
        default = db.scalars(select(Board.id).order_by(Board.id)).first()
        if default is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="no board exists; create one first",
            )
        return default
    if db.get(Board, board_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="board_id must reference an existing board",
        )
    return board_id


@router.get("", response_model=list[BoardRead])
def list_boards(
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> list[Board]:
    """List the boards the caller can see — owned **and** ones they're a member of
    (KAN-15). Each board carries the caller's effective ``role`` (owner → "owner",
    else the board_member role), attached transiently for the switcher's role
    badge (mirrors how ``MemberRead.email`` is attached in the members router)."""
    query = select(Board).order_by(Board.id).where(Board.id.in_(visible_board_ids(principal)))
    boards = list(db.scalars(query).all())
    # One lookup of the caller's member roles across all their boards.
    member_roles = dict(
        db.execute(
            select(BoardMember.board_id, BoardMember.role).where(
                BoardMember.user_id == principal.id
            )
        ).all()
    )
    for board in boards:
        board.role = (
            "owner" if board.owner_id == principal.id else member_roles.get(board.id)
        )
    return boards


@router.post("", response_model=BoardRead, status_code=status.HTTP_201_CREATED)
def create_board(
    payload: BoardCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Board:
    # Owner comes from the calling user, never the request body.
    board = Board(name=payload.name, owner_id=principal.id)
    db.add(board)
    db.commit()
    db.refresh(board)
    record_activity(
        db,
        principal,
        board_id=board.id,
        entity_type="board",
        entity_id=board.id,
        action="created",
        summary=f"created board {board.name}",
    )
    db.commit()
    return board


@router.get("/{board_id}", response_model=BoardRead)
def get_board(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Board:
    return authorize_board(db, principal, board_id, Access.READ)


@router.patch("/{board_id}", response_model=BoardRead)
def update_board(
    board_id: int,
    payload: BoardUpdate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Board:
    board = authorize_board(db, principal, board_id, Access.MANAGE)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and (data["name"] is None or not str(data["name"]).strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="name must not be empty",
        )
    for field, value in data.items():
        setattr(board, field, value)
    record_activity(
        db,
        principal,
        board_id=board.id,
        entity_type="board",
        entity_id=board.id,
        action="updated",
        summary=f"updated board {board.name}",
    )
    db.commit()  # updated_at bumped server-side via onupdate
    db.refresh(board)
    return board


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Response:
    board = authorize_board(db, principal, board_id, Access.MANAGE)
    # A board-deletion event is recorded for completeness, but it is keyed to the
    # board being deleted, whose ON DELETE CASCADE takes the whole audit trail —
    # including this row — with it. So the record is intentionally ephemeral: it is
    # written and then cascaded away in the same transaction (the board's history
    # dies with the board, by design).
    record_activity(
        db,
        principal,
        board_id=board.id,
        entity_type="board",
        entity_id=board.id,
        action="deleted",
        summary=f"deleted board {board.name}",
    )
    db.delete(board)
    db.commit()
    # Hard delete; the FK's ON DELETE CASCADE removes this board's cards + epics.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{board_id}/activity", response_model=list[ActivityRead])
def list_activity(
    board_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = None,
    actor: str | None = Query(
        default=None,
        description="filter to rows whose actor_label equals this (an email / agent handle)",
    ),
    action: str | None = Query(
        default=None,
        description="filter to rows with this action (created/updated/deleted/moved/restored/…)",
    ),
) -> list[Activity]:
    """The board's activity feed, **newest-first** (KAN-18, reading KAN-17's write
    path). One row per successful create / update / delete / move of a card, epic or
    board.

    **Member-scoped (``Access.READ`` — viewer or above):** the board owner and any
    member may read it; a non-member/non-owner gets ``403``, an unauthenticated
    caller ``401``, an unknown board ``404`` (via :func:`app.authz.authorize_board`).

    Optional filters (M5 V16, KAN-249), AND-ed with each other and with pagination:
    ``actor`` (exact match on ``actor_label`` — an actor's email / agent handle) and
    ``action`` (exact match on the action verb). Both narrow the feed so the
    awareness dashboard can slice it by *who* did *what*; the cursor still pages
    within the filtered result.

    Pagination mirrors ``GET /cards`` exactly: keyset over ``(ts, id)`` — but
    **descending**, since the feed is newest-first. Pass ``limit`` to cap the page;
    when a full page is returned the next page's opaque cursor rides the
    ``X-Next-Cursor`` response header (absent on the last page). Echo it back as
    ``cursor`` for the next request.
    """
    authorize_board(db, principal, board_id, Access.READ)
    query = (
        select(Activity)
        .where(Activity.board_id == board_id)
        .order_by(Activity.ts.desc(), Activity.id.desc())
    )
    if actor is not None:
        query = query.where(Activity.actor_label == actor)
    if action is not None:
        query = query.where(Activity.action == action)
    if cursor is not None:
        try:
            cursor_ts, cursor_id = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid cursor",
            ) from exc
        # Descending keyset: the next page is everything ordered *before* the cursor.
        query = query.where(tuple_(Activity.ts, Activity.id) < (cursor_ts, cursor_id))
    if limit is not None:
        query = query.limit(limit)

    rows = list(db.scalars(query).all())

    # A full page implies there may be more — hand back the next cursor. A short
    # (or empty) page is the last one, so no header.
    if limit is not None and len(rows) == limit:
        last = rows[-1]
        response.headers[NEXT_CURSOR_HEADER] = encode_cursor(last.ts, last.id)
    return rows


# --- dispatch + fleet-safe claim (M5 V12, KAN-245) -------------------------
#
# Agent-operate core: pull the next ready-to-work card off a board. ``next``
# peeks; ``dispatch`` atomically claims. The selection (todo, not blocked, ordered
# priority DESC then position, one row) lives in :func:`app.ordering.select_next_ready_card`
# so both share exactly one definition of "ready" (reusing the ``blocked`` predicate
# from ``routers/cards.py``, not re-deriving it). ``dispatch`` uses ``FOR UPDATE SKIP
# LOCKED`` so a whole fleet can dispatch concurrently and never collide on a card.


@router.get(
    "/{board_id}/next",
    response_model=CardRead,
    responses={204: {"description": "no card is ready to dispatch"}},
)
def peek_next(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
    label: int | None = None,
    priority: PriorityEnum | None = None,
):
    """**Peek** at the next ready-to-dispatch card on this board without claiming it
    (M5 V12, KAN-245) — the same selection as ``dispatch`` (next ``todo`` card not
    blocked by an open dependency, ordered ``priority DESC`` then ``position``) but
    read-only: no assignee change, no move, no lock. Returns the card, or **204 No
    Content** when nothing is ready.

    Optional filters (AND-ed): ``label`` (a label id) and ``priority`` (a *minimum*
    priority — only cards at that rank or above). ``Access.READ`` — a viewer may peek.
    """
    authorize_board(db, principal, board_id, Access.READ)
    card = select_next_ready_card(
        db,
        board_id,
        label=label,
        min_priority=priority.value if priority is not None else None,
        for_update=False,
    )
    if card is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    # Attach dependency arrays / links / labels so the body is a full CardRead
    # (lazy import: routers/cards.py imports this module, so it can't be top-level).
    from .cards import _attach_one

    return _attach_one(db, card)


@router.post(
    "/{board_id}/dispatch",
    response_model=CardRead,
    responses={204: {"description": "no card is ready to dispatch"}},
)
def dispatch_card(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
    payload: DispatchRequest | None = None,
):
    """**Dispatch** (atomically claim) the next ready-to-work card on this board in
    one transaction (M5 V12, KAN-245) — the agent-operate core.

    Selects the next ``todo`` card that is **not blocked** by an open dependency,
    ordered ``priority DESC`` (urgent first) then ``position ASC``, with ``FOR UPDATE
    SKIP LOCKED`` so concurrent dispatchers each lock-and-skip and never claim the
    same card (the fleet-safety mechanism — a DB row lock, not app locking; ADR
    0007). It then sets ``assignee`` (the body's ``assignee``, else the caller's
    identity), moves the card to ``in_progress`` (appended, with the source column
    renumbered), records a ``moved`` activity event, and returns the card. **204 No
    Content** when nothing is ready.

    Optional body filters (AND-ed with readiness): ``assignee`` (who to claim as),
    ``label`` (a label id), ``priority`` (a *minimum* priority). ``Access.WRITE`` —
    it mutates.
    """
    authorize_board(db, principal, board_id, Access.WRITE)
    req = payload or DispatchRequest()
    card = select_next_ready_card(
        db,
        board_id,
        label=req.label,
        min_priority=req.priority.value if req.priority is not None else None,
        for_update=True,
    )
    if card is None:
        # Nothing ready — release the (empty) FOR UPDATE scan and reply 204.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    assignee = req.assignee or principal.email
    source_column = card.column  # "todo"
    # Append to the end of in_progress. Computed before mutating card.column; with
    # autoflush off the count sees the DB (card still in todo), so it excludes this
    # very card and lands it cleanly at the end (mirrors move_card).
    new_position = next_position(db, board_id, ColumnEnum.in_progress.value)
    card.assignee = assignee
    card.column = ColumnEnum.in_progress.value
    card.position = new_position
    # Flush so the moved card's new column is visible to the source renumber query.
    db.flush()
    renumber_column(db, board_id, source_column)

    record_activity(
        db,
        principal,
        board_id=board_id,
        entity_type="card",
        entity_id=card.id,
        action="moved",
        summary=f"dispatched {card.ticket_number} to {assignee}",
    )
    # One transaction: the SELECT ... FOR UPDATE SKIP LOCKED row lock is held right
    # through here and released on commit, so the claim is atomic + fleet-safe.
    db.commit()
    db.refresh(card)
    from .cards import _attach_one

    return _attach_one(db, card)


# --- fleet reporting / metrics (M5 V17, KAN-250) ---------------------------
#
# Derived flow metrics for a board — throughput, cycle time, aging WIP, and a
# per-assignee breakdown — computed entirely from the activity feed (KAN-17/18)
# plus current card state. **No new write path and no migration**: reporting
# rides data already recorded. The pure derivation (parse move summaries →
# compute the numbers) lives in :mod:`app.metrics` so it unit-tests without a DB.

_WINDOW_RE = re.compile(r"^(?P<n>\d+)(?P<unit>[dhm])$")
_WINDOW_UNITS = {"d": "days", "h": "hours", "m": "minutes"}


def _resolve_since(since: datetime | None, window: str | None, now: datetime) -> datetime | None:
    """Resolve the reporting period's lower bound.

    ``since`` (an explicit ISO-8601 timestamp) wins; else ``window`` (a relative
    span like ``7d`` / ``24h`` / ``30m``) is subtracted from ``now``; else ``None``
    (all time). A malformed ``window`` is a 422."""
    if since is not None:
        return since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    if window is not None:
        match = _WINDOW_RE.match(window)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="window must look like '7d', '24h' or '30m'",
            )
        delta = timedelta(**{_WINDOW_UNITS[match.group("unit")]: int(match.group("n"))})
        return now - delta
    return None


@router.get("/{board_id}/metrics", response_model=BoardMetricsRead)
def board_metrics(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
    since: datetime | None = Query(
        default=None, description="ISO-8601 lower bound for the reporting period"
    ),
    window: str | None = Query(
        default=None,
        description="relative period, e.g. '7d' / '24h' / '30m' (ignored if 'since' is set)",
    ),
) -> BoardMetricsRead:
    """Derived fleet-reporting metrics for this board (M5 V17, KAN-250).

    Everything is computed on the fly from the activity feed + card timestamps —
    there is no stored metric and no migration. ``Access.READ`` (viewer or above);
    unknown board 404, no access 403, unauthenticated 401.

    The period is ``[since, now]``: pass ``since`` (an ISO-8601 timestamp) or the
    convenience ``window`` (``7d``/``24h``/``30m``); omit both for all time. Reports:

    - **throughput** — cards that reached ``done`` in the period;
    - **cycle_time** — first ``in_progress`` → ``done`` (avg/median/p90 seconds);
    - **aging_wip** — how long each currently-``in_progress`` card has sat there;
    - **by_assignee** — completed + open WIP per assignee.

    A quiet/empty board returns zeros and nulls (never an error).
    """
    authorize_board(db, principal, board_id, Access.READ)
    now = datetime.now(timezone.utc)
    period_since = _resolve_since(since, window, now)

    # Column transitions, recovered from the "moved" activity rows' summaries (the
    # model stores no structured target column — see app.metrics.parse_move_target).
    move_rows = db.execute(
        select(Activity.entity_id, Activity.summary, Activity.ts).where(
            Activity.board_id == board_id,
            Activity.entity_type == "card",
            Activity.action == "moved",
        )
    ).all()
    transitions = [
        (entity_id, target, ts)
        for entity_id, summary, ts in move_rows
        if (target := parse_move_target(summary)) is not None
    ]

    # Current card state (all rows, incl. soft-deleted, for assignee lookup; the
    # metrics themselves exclude deleted cards from live WIP).
    card_rows = db.execute(
        select(
            Card.id,
            Card.ticket_number,
            Card.column,
            Card.assignee,
            Card.created_at,
            Card.deleted_at,
        ).where(Card.board_id == board_id)
    ).all()
    cards = [
        {
            "id": row.id,
            "ticket_number": row.ticket_number,
            "column": row.column,
            "assignee": row.assignee,
            "created_at": row.created_at,
            "deleted": row.deleted_at is not None,
        }
        for row in card_rows
    ]

    metrics = compute_metrics(transitions, cards, now=now, since=period_since)
    return BoardMetricsRead(
        board_id=board_id,
        generated_at=now,
        since=period_since,
        until=now,
        **metrics,
    )
