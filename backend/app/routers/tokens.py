"""Personal-access-token endpoints (M3 V9, ADR 0014).

Self-serve agent tokens (R4.1): a user creates named tokens, sees each secret
**once**, and revokes them. A token authenticates as its owning user and inherits
that user's board access (ADR 0013) — so there is no per-token board/scope (D5;
scoping is R4.2 / Later). Mounted under ``/api/v1``:

- GET    /tokens       — list the caller's tokens (metadata only, never the secret)
- POST   /tokens       — create a token; response includes the secret **once**
- DELETE /tokens/{id}  — revoke (hard-delete) one of the caller's tokens

Every route is **per-user**: it requires an authenticated ``User`` principal
(cookie session or a PAT) — see :func:`app.authz.require_user`. Since V10 (ADR
0015) every principal is a real user, so ``require_user`` is just ``get_principal``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_models import PersonalAccessToken, User
from ..authz import require_user
from ..db import get_db
from ..schemas import TokenCreate, TokenCreated, TokenRead
from ..tokens import generate_token

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("", response_model=list[TokenRead])
def list_tokens(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[PersonalAccessToken]:
    return list(
        db.scalars(
            select(PersonalAccessToken)
            .where(PersonalAccessToken.user_id == user.id)
            .order_by(PersonalAccessToken.id)
        ).all()
    )


@router.post("", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    payload: TokenCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> TokenCreated:
    raw, prefix, token_hash = generate_token()
    pat = PersonalAccessToken(
        user_id=user.id,
        name=payload.name,
        token_hash=token_hash,
        token_prefix=prefix,
        expires_at=payload.expires_at,
    )
    db.add(pat)
    db.commit()
    db.refresh(pat)
    # The only time the raw secret is ever returned (R7.1).
    return TokenCreated(
        id=pat.id,
        name=pat.name,
        token_prefix=pat.token_prefix,
        created_at=pat.created_at,
        last_used_at=pat.last_used_at,
        expires_at=pat.expires_at,
        token=raw,
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Response:
    pat = db.get(PersonalAccessToken, token_id)
    # 404 (not 403) for someone else's token: don't reveal that the id exists.
    if pat is None or pat.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    db.delete(pat)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
