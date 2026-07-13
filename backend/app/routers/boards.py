"""Boards endpoints (M3 V7, ADR 0012; **owner-gated in V8, ADR 0013**).

A board is a first-class entity owning a set of cards + epics. Full CRUD, mirroring
the flat structure of the cards/epics routers (API-first, ADR 0005). Mounted by
``main.py`` under ``/api/v1`` (e.g. ``/api/v1/boards``):

- GET    /boards       — list the caller's boards
- POST   /boards       — create a board (owner = the calling user)
- GET    /boards/{id}  — read one board (viewer or above)
- PATCH  /boards/{id}  — rename (owner only)
- DELETE /boards/{id}  — hard-delete; its cards + epics cascade away (owner only)

**Authorization (V8 + KAN-13, ADR 0013):** every route requires a principal (`401`
otherwise). Reads are ``Access.READ`` (viewer or above); rename/delete are
``Access.MANAGE`` (owner only). The list stays owner-scoped (member visibility is
KAN-15). See :mod:`app.authz`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_models import User
from ..authz import Access, authorize_board, get_principal, visible_board_ids
from ..db import get_db
from ..models import Board
from ..schemas import BoardCreate, BoardRead, BoardUpdate

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
    query = select(Board).order_by(Board.id).where(Board.id.in_(visible_board_ids(principal)))
    return list(db.scalars(query).all())


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
    db.delete(board)
    db.commit()
    # Hard delete; the FK's ON DELETE CASCADE removes this board's cards + epics.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
