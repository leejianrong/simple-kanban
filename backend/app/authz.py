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

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from .auth import bearer_scheme
from .auth_models import PersonalAccessToken, User
from .db import get_db
from .models import Board
from .tokens import TOKEN_PREFIX, hash_token
from .users import current_optional_user


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


def authorize_board(db: Session, principal: User, board_id: int) -> Board:
    """Load ``board_id`` and assert the principal may act on it, else raise.

    404 if the board doesn't exist; 403 if the principal doesn't own it. Returns
    the loaded board so callers can reuse it.
    """
    board = db.get(Board, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    if board.owner_id != principal.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you do not have access to this board",
        )
    return board


def visible_board_ids(principal: User) -> Select:
    """A scalar subquery of the board ids this principal may see. Used to scope
    list endpoints so a caller only ever sees their own boards/cards/epics."""
    return select(Board.id).where(Board.owner_id == principal.id)
