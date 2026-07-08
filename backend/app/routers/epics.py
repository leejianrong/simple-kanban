"""Epics endpoints (ADR 0009).

Epics are a board-less grouping a story can belong to — created and read in a
separate UI surface, not on the kanban board. Full CRUD, mirroring the flat
structure of the cards router (API-first, ADR 0005). Mounted by ``main.py`` under
``/api/v1`` (canonical) and ``/api`` (compat alias); paths below are relative:

- GET    /epics       — list all epics (newest ticket first)
- POST   /epics       — create an epic (EPIC-<n> assigned by the DB)
- GET    /epics/{id}  — read one epic
- PATCH  /epics/{id}  — edit fields (name/description)
- DELETE /epics/{id}  — hard-delete; child stories are detached (epic_id → NULL)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Epic
from ..schemas import EpicCreate, EpicRead, EpicUpdate

router = APIRouter(prefix="/epics", tags=["epics"])


def _get_or_404(db: Session, epic_id: int) -> Epic:
    epic = db.get(Epic, epic_id)
    if epic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Epic not found")
    return epic


@router.get("", response_model=list[EpicRead])
def list_epics(db: Session = Depends(get_db)) -> list[Epic]:
    return list(db.scalars(select(Epic).order_by(Epic.id)).all())


@router.post("", response_model=EpicRead, status_code=status.HTTP_201_CREATED)
def create_epic(payload: EpicCreate, db: Session = Depends(get_db)) -> Epic:
    epic = Epic(name=payload.name, description=payload.description)
    db.add(epic)
    db.commit()
    # Refresh so server-assigned fields (id, ticket_number, timestamps) are populated.
    db.refresh(epic)
    return epic


@router.get("/{epic_id}", response_model=EpicRead)
def get_epic(epic_id: int, db: Session = Depends(get_db)) -> Epic:
    return _get_or_404(db, epic_id)


@router.patch("/{epic_id}", response_model=EpicRead)
def update_epic(
    epic_id: int, payload: EpicUpdate, db: Session = Depends(get_db)
) -> Epic:
    epic = _get_or_404(db, epic_id)
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
def delete_epic(epic_id: int, db: Session = Depends(get_db)) -> Response:
    epic = _get_or_404(db, epic_id)
    db.delete(epic)
    db.commit()
    # Hard delete; child stories are detached via the FK's ON DELETE SET NULL.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
