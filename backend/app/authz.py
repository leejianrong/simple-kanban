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

from typing import Union

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from .auth import bearer_scheme, configured_tokens
from .auth_models import User
from .models import Board
from .users import current_optional_user


class _Service:
    """Sentinel for the transitional ``API_TOKENS`` service principal (bypasses
    the owner check). A distinct type so ``isinstance`` reads clearly."""

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "SERVICE"


SERVICE = _Service()

# A resolved principal is either a human User or the SERVICE sentinel.
Principal = Union[User, _Service]


def get_principal(
    user: User | None = Depends(current_optional_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    """Resolve the request principal, or 401 if there is none.

    Precedence: a human cookie session wins; failing that, a valid ``API_TOKENS``
    bearer yields the SERVICE principal. Anything else is unauthenticated.
    """
    if user is not None:
        return user
    tokens = configured_tokens()
    if tokens and credentials is not None and credentials.credentials in tokens:
        return SERVICE
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
