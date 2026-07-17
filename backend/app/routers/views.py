"""Saved-view endpoints (M5 V14, KAN-247; owner/member-gated, ADR 0013).

A saved view is a named, persisted card query on a board (``schemas.CardQuery``
stored as JSON). Replaying its stored ``query`` as ``GET /cards`` query params
reproduces its result set — the view holds a *query*, not a snapshot of rows.
Full CRUD-lite, mirroring the flat structure of the labels router (API-first,
ADR 0005). Mounted by ``main.py`` under ``/api/v1``:

- GET    /boards/{board_id}/views           — list a board's saved views (viewer+)
- POST   /boards/{board_id}/views           — create a saved view (editor+)
- GET    /boards/{board_id}/views/{view_id} — read one saved view (viewer+)
- DELETE /boards/{board_id}/views/{view_id} — delete a saved view (editor+)

Every view is addressed under its board (``/boards/{id}/views``); the board gates
access via ``authorize_board`` (READ to list/get, WRITE to create/delete). A view
whose ``board_id`` doesn't match the path board **404s** — so a cross-board id is
never reachable through another board you happen to own. No activity-log rows: the
audit feed's CHECK vocabulary covers card/epic/board entities only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_models import User
from ..authz import Access, authorize_board, get_principal
from ..db import get_db
from ..models import SavedView
from ..schemas import SavedViewCreate, SavedViewRead

router = APIRouter(tags=["views"])


def _get_view_or_404(db: Session, board_id: int, view_id: int) -> SavedView:
    """Load saved view ``view_id`` **on ``board_id``**; 404 if it doesn't exist or
    belongs to a different board (so a cross-board id is never reachable)."""
    view = db.get(SavedView, view_id)
    if view is None or view.board_id != board_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found"
        )
    return view


@router.get("/boards/{board_id}/views", response_model=list[SavedViewRead])
def list_views(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> list[SavedView]:
    """List a board's saved views, oldest-first (creation order). Viewer or above;
    a board you can't see is a ``403`` (unknown board ``404``)."""
    authorize_board(db, principal, board_id, Access.READ)
    return list(
        db.scalars(
            select(SavedView)
            .where(SavedView.board_id == board_id)
            .order_by(SavedView.id)
        ).all()
    )


@router.post(
    "/boards/{board_id}/views",
    response_model=SavedViewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_view(
    board_id: int,
    payload: SavedViewCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> SavedView:
    """Create a saved view on a board (editor or above). ``name`` + ``query`` come
    from the body; the board from the path. The ``query`` (the filter+sort grammar)
    is validated by ``CardQuery`` and stored as JSON (``exclude_none`` so only the
    set filters are persisted — a compact, replayable param set)."""
    authorize_board(db, principal, board_id, Access.WRITE)
    view = SavedView(
        board_id=board_id,
        name=payload.name,
        query=payload.query.model_dump(mode="json", exclude_none=True),
    )
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


@router.get("/boards/{board_id}/views/{view_id}", response_model=SavedViewRead)
def get_view(
    board_id: int,
    view_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> SavedView:
    """Read one saved view (viewer or above). **404** if it doesn't exist or isn't
    on this board; **403** if the board isn't yours."""
    authorize_board(db, principal, board_id, Access.READ)
    return _get_view_or_404(db, board_id, view_id)


@router.delete(
    "/boards/{board_id}/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_view(
    board_id: int,
    view_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Response:
    """Delete a saved view (editor or above on its board). **404** if no such view
    on this board; **403** if the board isn't yours."""
    authorize_board(db, principal, board_id, Access.WRITE)
    view = _get_view_or_404(db, board_id, view_id)
    db.delete(view)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
