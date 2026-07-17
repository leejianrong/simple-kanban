"""Label endpoints (M5 V11, KAN-244; owner/member-gated, ADR 0013).

Labels are board-scoped, colored tags a card can carry (R4.2). Full CRUD-lite,
mirroring the flat structure of the cards/epics routers (API-first, ADR 0005).
Mounted by ``main.py`` under ``/api/v1``:

- GET    /boards/{board_id}/labels — list a board's labels (viewer or above)
- POST   /boards/{board_id}/labels — create a label on a board (editor or above)
- DELETE /labels/{label_id}        — delete a label (editor or above); it detaches
                                     from every card via ON DELETE CASCADE

Create/list are addressed by board (``/boards/{id}/labels``); delete is addressed
by the label's own id (``/labels/{id}``) and authorized via the label's board — the
cleanest shape for the two access patterns. No activity log rows: the audit feed's
CHECK vocabulary covers card/epic/board entities only, and a label is neither.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_models import User
from ..authz import Access, authorize_board, get_principal
from ..db import get_db
from ..models import Label
from ..schemas import LabelCreate, LabelRead

router = APIRouter(tags=["labels"])


def _get_label_or_404(db: Session, label_id: int) -> Label:
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Label not found"
        )
    return label


@router.get("/boards/{board_id}/labels", response_model=list[LabelRead])
def list_labels(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> list[Label]:
    """List a board's labels, oldest-first (creation order). Viewer or above; a
    board you can't see is a ``403`` (unknown board ``404``)."""
    authorize_board(db, principal, board_id, Access.READ)
    return list(
        db.scalars(
            select(Label).where(Label.board_id == board_id).order_by(Label.id)
        ).all()
    )


@router.post(
    "/boards/{board_id}/labels",
    response_model=LabelRead,
    status_code=status.HTTP_201_CREATED,
)
def create_label(
    board_id: int,
    payload: LabelCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Label:
    """Create a label on a board (editor or above). ``name`` + ``color`` come from
    the body; the board from the path."""
    authorize_board(db, principal, board_id, Access.WRITE)
    label = Label(board_id=board_id, name=payload.name, color=payload.color)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


@router.delete("/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    label_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Response:
    """Delete a label by id (editor or above on its board). Its ``card_label`` join
    rows cascade away, so it detaches from every card that carried it. **404** if no
    such label; **403** if the label's board isn't yours."""
    label = _get_label_or_404(db, label_id)
    authorize_board(db, principal, label.board_id, Access.WRITE)
    db.delete(label)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
