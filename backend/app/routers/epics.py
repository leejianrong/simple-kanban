"""Epics endpoints (ADR 0009; **owner-gated in V8, ADR 0013**).

Epics are a per-board grouping a story can belong to — one board owns many epics,
one epic groups many stories (all on that board). Created and read in a separate UI
surface, not on the kanban board. Full CRUD, mirroring the flat structure of the
cards router (API-first, ADR 0005). Mounted by ``main.py`` under ``/api/v1``:

- GET    /epics       — list the caller's epics (optionally scoped to one board)
- POST   /epics       — create an epic (EPIC-<n> assigned by the DB)
- GET    /epics/{id}  — read one epic
- PATCH  /epics/{id}  — edit fields (name/description)
- DELETE /epics/{id}  — hard-delete; child stories are detached (epic_id → NULL)

**Authorization (V8):** every route requires a principal (`401` otherwise) and
that the principal own the epic's board (`403`); the list is scoped to the caller's
boards. See :mod:`app.authz`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authz import Principal, authorize_board, get_principal, visible_board_ids
from ..db import get_db
from ..models import Epic
from ..schemas import EpicCreate, EpicRead, EpicUpdate
from .boards import resolve_board_id

router = APIRouter(prefix="/epics", tags=["epics"])


def _get_or_404(db: Session, epic_id: int) -> Epic:
    epic = db.get(Epic, epic_id)
    if epic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Epic not found")
    return epic


@router.get("", response_model=list[EpicRead])
def list_epics(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    board_id: int | None = None,
) -> list[Epic]:
    """List epics, owner-scoped (V8) and optionally scoped to one board. A
    ``board_id`` you don't own is a ``403``; omitted → all *your* boards' epics
    (the SPA always sends it to scope the Epics view)."""
    query = select(Epic).order_by(Epic.id)
    if board_id is not None:
        authorize_board(db, principal, board_id)
        query = query.where(Epic.board_id == board_id)
    else:
        scope = visible_board_ids(principal)
        if scope is not None:
            query = query.where(Epic.board_id.in_(scope))
    return list(db.scalars(query).all())


@router.post("", response_model=EpicRead, status_code=status.HTTP_201_CREATED)
def create_epic(
    payload: EpicCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Epic:
    board_id = resolve_board_id(db, payload.board_id)
    authorize_board(db, principal, board_id)
    epic = Epic(
        board_id=board_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(epic)
    db.commit()
    # Refresh so server-assigned fields (id, ticket_number, timestamps) are populated.
    db.refresh(epic)
    return epic


@router.get("/{epic_id}", response_model=EpicRead)
def get_epic(
    epic_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Epic:
    epic = _get_or_404(db, epic_id)
    authorize_board(db, principal, epic.board_id)
    return epic


@router.patch("/{epic_id}", response_model=EpicRead)
def update_epic(
    epic_id: int,
    payload: EpicUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Epic:
    epic = _get_or_404(db, epic_id)
    authorize_board(db, principal, epic.board_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and (data["name"] is None or not str(data["name"]).strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="name must not be empty",
        )
    for field, value in data.items():
        setattr(epic, field, value)
    db.commit()  # updated_at is bumped server-side via onupdate
    db.refresh(epic)
    return epic


@router.delete("/{epic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_epic(
    epic_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Response:
    epic = _get_or_404(db, epic_id)
    authorize_board(db, principal, epic.board_id)
    db.delete(epic)
    db.commit()
    # Hard delete; child stories are detached via the FK's ON DELETE SET NULL.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
