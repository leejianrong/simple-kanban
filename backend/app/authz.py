"""Board authorization — the one authz layer (M3 V8, ADR 0013, Shape A5 / D3).

V8 makes the whole ``/api/v1`` surface **auth-required and owner-scoped**. This is
a deliberate, documented contract change (R3.4): every board-scoped read and write
now resolves a **principal** and checks it against the target board's owner.

Two principals feed one check (BREADBOARD S5 "principal resolver"):

- **Human** — a valid ``kanbanauth`` cookie session → a ``User`` (via
  fastapi-users' ``current_optional_user``, on the async engine). Owner-gated: may
  only touch boards whose ``owner_id`` is their id.
- **SERVICE** — a valid ``API_TOKENS`` bearer → a sentinel that **bypasses** the
  owner check entirely. Transitional: the MCP server still uses the shared
  ``API_TOKENS`` bearer (not a per-user token) during the V8→V9 window; V9 replaces
  it with per-user PATs that resolve to a real ``User`` (ADR 0010 → superseded).

No principal → **401**. A human principal that doesn't own the target board →
**403**. The board CRUD stays on the sync engine (ADR 0008): the sync board routes
depend on the async ``current_optional_user`` — FastAPI resolves the async
sub-dependency for a sync endpoint (proven in V7's ``create_board``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from .auth import bearer_scheme, configured_tokens
from .auth_models import PersonalAccessToken, User
from .db import get_db
from .models import Board
from .tokens import TOKEN_PREFIX, hash_token
from .users import current_optional_user


class _Service:
    """Sentinel for the transitional ``API_TOKENS`` service principal (bypasses
    the owner check). A distinct type so ``isinstance`` reads clearly."""

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "SERVICE"


SERVICE = _Service()

# A resolved principal is either a human User or the SERVICE sentinel.
Principal = Union[User, _Service]


def _resolve_pat(db: Session, raw: str) -> User | None:
    """Resolve a bearer value to its owning ``User`` if it is a valid, unexpired
    personal access token (M3 V9, ADR 0014), else ``None``.

    Fully **sync** (ADR 0008): our own table, an indexed lookup by hash. Stamps
    ``last_used_at`` on success. Revocation is deletion, so a revoked token simply
    isn't found.
    """
    # Fast-path skip: only strings minted by us can match, so a stray API_TOKENS
    # value never triggers a DB round-trip.
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
) -> Principal:
    """Resolve the request principal, or 401 if there is none.

    Precedence: a human **cookie session** wins; else a valid **personal access
    token** bearer → its owning ``User`` (V9, owner-gated like a human); else a
    valid **``API_TOKENS``** bearer → the transitional SERVICE bypass (removed in
    V10). Anything else is unauthenticated.
    """
    if user is not None:
        return user
    if credentials is not None:
        pat_user = _resolve_pat(db, credentials.credentials)
        if pat_user is not None:
            return pat_user
        tokens = configured_tokens()
        if credentials.credentials in tokens:
            return SERVICE
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_user(principal: Principal = Depends(get_principal)) -> User:
    """Like :func:`get_principal` but rejects the SERVICE principal — for routes
    that are inherently per-user (e.g. token management). 403 for SERVICE."""
    if not isinstance(principal, User):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this action requires a user account",
        )
    return principal


def authorize_board(db: Session, principal: Principal, board_id: int) -> Board:
    """Load ``board_id`` and assert the principal may act on it, else raise.

    404 if the board doesn't exist; 403 if a human principal doesn't own it. The
    SERVICE principal bypasses the owner check. Returns the loaded board so callers
    can reuse it.
    """
    board = db.get(Board, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    if principal is SERVICE:
        return board
    if board.owner_id != principal.id:  # type: ignore[union-attr]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you do not have access to this board",
        )
    return board


def visible_board_ids(principal: Principal) -> Select | None:
    """A scalar subquery of the board ids this principal may see, or ``None`` to
    mean "all boards" (the SERVICE principal). Used to scope list endpoints so a
    caller only ever sees their own boards/cards/epics."""
    if principal is SERVICE:
        return None
    return select(Board.id).where(Board.owner_id == principal.id)  # type: ignore[union-attr]
