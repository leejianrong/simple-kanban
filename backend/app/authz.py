"""Board authorization — the one authz layer (M3 V8, ADR 0013; V10, ADR 0015).

V8 made the whole ``/api/v1`` surface **auth-required and owner-scoped**: every
board-scoped read and write resolves a **principal** and checks it against the
target board's owner (R3.4).

**V10 (ADR 0015)** retires the transitional ``API_TOKENS`` SERVICE bypass V8 left
in place. Now there is exactly one kind of principal — a real ``User`` — reached
two ways (BREADBOARD S5 "principal resolver"):

- **Human** — a valid ``kanbanauth`` cookie session → a ``User`` (via
  fastapi-users' ``current_optional_user``, on the async engine).
- **Agent** — a valid **personal access token** bearer → its owning ``User``
  (V9, ADR 0014; sync lookup on our own table).

Either way the principal is owner-gated: it may only touch boards whose
``owner_id`` is its id. No principal → **401**; a principal that doesn't own the
target board → **403**. The board CRUD stays on the sync engine (ADR 0008): the
sync board routes depend on the async ``current_optional_user`` — FastAPI resolves
the async sub-dependency for a sync endpoint (proven in V7's ``create_board``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from .auth import bearer_scheme
from .auth_models import PersonalAccessToken, User
from .db import get_db
from .models import Board, BoardMember
from .tokens import TOKEN_PREFIX, hash_token
from .users import current_optional_user


class Access(IntEnum):
    """The capability a board-scoped action requires (KAN-13).

    Ordered so a ``>=`` comparison *is* the authorization check: a principal's
    effective access must be **at least** the level the action demands.

    - ``READ`` — viewer or above: GET/list/read of a board's cards/epics/members.
    - ``WRITE`` — editor or above: create/update/move/delete cards + epics.
    - ``MANAGE`` — owner only: board rename/delete + member management.
    """

    READ = 1
    WRITE = 2
    MANAGE = 3


# A board_member role maps to the highest :class:`Access` level it grants. The
# board OWNER (``board.owner_id``) is always treated as ``MANAGE`` regardless of
# any membership row.
_ROLE_ACCESS: dict[str, Access] = {
    "viewer": Access.READ,
    "editor": Access.WRITE,
    "owner": Access.MANAGE,
}


def _resolve_pat(db: Session, raw: str) -> User | None:
    """Resolve a bearer value to its owning ``User`` if it is a valid, unexpired
    personal access token (M3 V9, ADR 0014), else ``None``.

    Fully **sync** (ADR 0008): our own table, an indexed lookup by hash. Stamps
    ``last_used_at`` on success. Revocation is deletion, so a revoked token simply
    isn't found.
    """
    # Fast-path skip: only strings minted by us can match, so a stray bearer never
    # triggers a DB round-trip.
    if not raw.startswith(TOKEN_PREFIX):
        return None
    pat = db.scalars(
        select(PersonalAccessToken).where(
            PersonalAccessToken.token_hash == hash_token(raw)
        )
    ).first()
    if pat is None:
        return None
    if pat.expires_at is not None and pat.expires_at <= datetime.now(timezone.utc):
        return None
    pat.last_used_at = func.now()  # server-clock stamp; committed below
    db.commit()
    return db.get(User, pat.user_id)


def get_principal(
    user: User | None = Depends(current_optional_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the request principal (always a real ``User``), or 401 if none.

    Precedence: a human **cookie session** wins; else a valid **personal access
    token** bearer → its owning ``User`` (V9, owner-gated like a human). Anything
    else is unauthenticated.
    """
    if user is not None:
        return user
    if credentials is not None:
        pat_user = _resolve_pat(db, credentials.credentials)
        if pat_user is not None:
            return pat_user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Every principal is now a real user, so per-user routes (e.g. token management)
# use ``get_principal`` directly; ``require_user`` remains as a self-documenting
# alias for routes that are inherently about the acting user.
require_user = get_principal


def _effective_access(db: Session, principal: User, board: Board) -> Access | None:
    """The principal's effective :class:`Access` on ``board``, or ``None`` if it
    has no access at all.

    The board OWNER always has ``MANAGE`` (full access), regardless of any
    membership row (KAN-13). Otherwise the principal's ``board_member`` role, if
    any, decides. No ownership and no membership row → ``None`` (→ 403).
    """
    if board.owner_id == principal.id:
        return Access.MANAGE
    role = db.scalar(
        select(BoardMember.role).where(
            BoardMember.board_id == board.id,
            BoardMember.user_id == principal.id,
        )
    )
    if role is None:
        return None
    # An unknown role (should never happen — CHECK-constrained) grants nothing.
    return _ROLE_ACCESS.get(role)


def authorize_board(
    db: Session, principal: User, board_id: int, require: Access = Access.READ
) -> Board:
    """Load ``board_id`` and assert the principal has at least ``require`` access,
    else raise. Returns the loaded board so callers can reuse it.

    Role-aware (KAN-13, ADR 0013 — the *one* authz layer, no ad-hoc checks): the
    board owner has full (``MANAGE``) access; other principals get the access their
    ``board_member`` role grants (viewer→READ, editor→WRITE, owner→MANAGE).

    - **404** if the board doesn't exist.
    - **403** if the principal has no access to it, or less than ``require``.
    """
    board = db.get(Board, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    access = _effective_access(db, principal, board)
    if access is None or access < require:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you do not have access to this board",
        )
    return board


def visible_board_ids(principal: User) -> Select:
    """A scalar subquery of the board ids this principal may see. Used to scope
    list endpoints so a caller only ever sees boards they have access to.

    A board is visible if the principal **owns** it *or* is a ``board_member`` of
    it (KAN-15) — the same set of boards :func:`authorize_board` grants at least
    ``READ`` on. Kept as a ``Select`` so callers can use it as an ``IN`` subquery
    unchanged."""
    return select(Board.id).where(
        or_(
            Board.owner_id == principal.id,
            Board.id.in_(
                select(BoardMember.board_id).where(BoardMember.user_id == principal.id)
            ),
        )
    )
