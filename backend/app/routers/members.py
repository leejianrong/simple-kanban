"""Board-membership endpoints (KAN-12).

A board can have members (users other than the owner) with a role — ``viewer`` /
``editor`` / ``owner`` (see :data:`app.models.VALID_ROLES`). Enforcement goes through
the one authz layer (:func:`app.authz.authorize_board`, ADR 0013): **managing members
is owner-only** (``Access.MANAGE``), while **listing members is read-gated**
(``Access.READ`` — any member may see who else is on the board, KAN-13). List
*visibility* scoping (KAN-15) is a separate slice.

Mounted by ``main.py`` under ``/api/v1`` (e.g. ``/api/v1/boards/{id}/members``):

- GET    /boards/{board_id}/members             — list members (viewer or above)
- POST   /boards/{board_id}/members             — add a member by user_id or email (owner only)
- PATCH  /boards/{board_id}/members/{member_id} — change a member's role (owner only)
- DELETE /boards/{board_id}/members/{member_id} — remove a member (owner only)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth_models import User
from ..authz import Access, authorize_board, get_principal
from ..db import get_db
from ..models import BoardMember
from ..schemas import MemberCreate, MemberRead, MemberUpdate

# The board id lives in the prefix so every route is naturally scoped to it.
router = APIRouter(prefix="/boards/{board_id}/members", tags=["members"])


def _with_email(db: Session, member: BoardMember) -> BoardMember:
    """Attach the member's email transiently (not an ORM column) so ``MemberRead``
    can surface it. One lookup on the shared user table via the sync engine."""
    member.email = db.scalar(select(User.email).where(User.id == member.user_id))
    return member


def _resolve_user(db: Session, payload: MemberCreate) -> User:
    """Resolve the target user from ``user_id`` or ``email`` (the schema guarantees
    exactly one is set); 404 if no such user exists."""
    if payload.user_id is not None:
        user = db.get(User, payload.user_id)
    else:
        # Case-insensitive, matching fastapi-users' own email lookup.
        user = db.scalars(
            select(User).where(func.lower(User.email) == payload.email.lower())
        ).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _get_member_or_404(db: Session, board_id: int, member_id: int) -> BoardMember:
    member = db.get(BoardMember, member_id)
    if member is None or member.board_id != board_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )
    return member


@router.get("", response_model=list[MemberRead])
def list_members(
    board_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> list[BoardMember]:
    """List a board's members, oldest-first. Read-gated (viewer or above);
    401/403/404 (KAN-13)."""
    authorize_board(db, principal, board_id, Access.READ)
    rows = db.execute(
        select(BoardMember, User.email)
        .join(User, User.id == BoardMember.user_id)
        .where(BoardMember.board_id == board_id)
        .order_by(BoardMember.id)
    ).all()
    members: list[BoardMember] = []
    for member, email in rows:
        member.email = email
        members.append(member)
    return members


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def add_member(
    board_id: int,
    payload: MemberCreate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> BoardMember:
    """Add a member to the board by ``user_id`` or ``email`` (KAN-12). Manage-gated
    (owner only, KAN-13). **404** if the target user doesn't exist; **409** if they
    are already a member."""
    authorize_board(db, principal, board_id, Access.MANAGE)
    user = _resolve_user(db, payload)
    existing = db.scalars(
        select(BoardMember).where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == user.id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user is already a member of this board",
        )
    member = BoardMember(board_id=board_id, user_id=user.id, role=payload.role.value)
    db.add(member)
    db.commit()
    db.refresh(member)
    member.email = user.email
    return member


@router.patch("/{member_id}", response_model=MemberRead)
def update_member(
    board_id: int,
    member_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> BoardMember:
    """Change a member's role (KAN-12). Manage-gated (owner only, KAN-13). **404** if
    no such member is on the board."""
    authorize_board(db, principal, board_id, Access.MANAGE)
    member = _get_member_or_404(db, board_id, member_id)
    member.role = payload.role.value
    db.commit()  # updated_at bumped server-side via onupdate
    db.refresh(member)
    return _with_email(db, member)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    board_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    principal: User = Depends(get_principal),
) -> Response:
    """Remove a member from the board (KAN-12). Manage-gated (owner only, KAN-13).
    **404** if no such member is on the board."""
    authorize_board(db, principal, board_id, Access.MANAGE)
    member = _get_member_or_404(db, board_id, member_id)
    db.delete(member)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
