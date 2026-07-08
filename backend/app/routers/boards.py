"""Boards endpoints (M3 V7, ADR 0012).

A board is a first-class entity owning a set of cards + epics. Full CRUD, mirroring
the flat structure of the cards/epics routers (API-first, ADR 0005). Mounted by
``main.py`` under ``/api/v1`` (e.g. ``/api/v1/boards``):

- GET    /boards       — list all boards
- POST   /boards       — create a board (owner = the session user, if any)
- GET    /boards/{id}  — read one board
- PATCH  /boards/{id}  — rename
- DELETE /boards/{id}  — hard-delete; its cards + epics cascade away (ON DELETE CASCADE)

**No authorization yet** (V7). Any request may list/read/write any board; the
owner is captured on create so V8's ownership check has real data to enforce.
Listing is likewise unscoped until V8.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_token
from ..auth_models import User
from ..db import get_db
from ..models import Board
from ..schemas import BoardCreate, BoardRead, BoardUpdate
from ..users import current_optional_user

router = APIRouter(prefix="/boards", tags=["boards"])


def _get_or_404(db: Session, board_id: int) -> Board:
    board = db.get(Board, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    return board


def resolve_board_id(db: Session, board_id: int | None) -> int:
    """Resolve the target board for a card/epic write.

    ``None`` → the default board (the earliest one), so pre-board clients keep
    working. A supplied id must reference an existing board (422). 409 if no board
    exists at all to default to.
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
def list_boards(db: Session = Depends(get_db)) -> list[Board]:
    return list(db.scalars(select(Board).order_by(Board.id)).all())


@router.post(
    "",
    response_model=BoardRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_token)],
)
def create_board(
    payload: BoardCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_optional_user),
) -> Board:
    # Owner comes from the session (if signed in), never the request body — an
    # unclaimed board (owner_id NULL) is fine for a tokenless/agent caller.
    board = Board(name=payload.name, owner_id=user.id if user else None)
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


@router.get("/{board_id}", response_model=BoardRead)
def get_board(board_id: int, db: Session = Depends(get_db)) -> Board:
    return _get_or_404(db, board_id)


@router.patch(
    "/{board_id}",
    response_model=BoardRead,
    dependencies=[Depends(require_token)],
)
def update_board(board_id: int, payload: BoardUpdate, db: Session = Depends(get_db)) -> Board:
    board = _get_or_404(db, board_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and (data["name"] is None or not str(data["name"]).strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="name must not be empty",
        )
    for field, value in data.items():
        setattr(board, field, value)
    db.commit()  # updated_at bumped server-side via onupdate
    db.refresh(board)
    return board


@router.delete(
    "/{board_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_token)],
)
def delete_board(board_id: int, db: Session = Depends(get_db)) -> Response:
    board = _get_or_404(db, board_id)
    db.delete(board)
    db.commit()
    # Hard delete; the FK's ON DELETE CASCADE removes this board's cards + epics.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
