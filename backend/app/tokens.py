"""Personal-access-token generation + hashing (M3 V9, ADR 0014).

A PAT is a high-entropy random secret shown to the user **once**; the DB stores
only its hash (R7.1). We use **HMAC-SHA256 keyed with ``AUTH_SECRET``** (a pepper):

- *Deterministic + indexable* — auth is a single ``WHERE token_hash = :h`` lookup,
  not an O(n) scan. (Password hashes like bcrypt salt per row and can't be looked
  up; they exist to slow brute force on low-entropy passwords — a 256-bit random
  token doesn't need that.)
- *Peppered* — a stolen database alone can't be used to verify guessed tokens
  offline without also stealing ``AUTH_SECRET``.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from .users import AUTH_SECRET

# Human-readable, greppable marker so a leaked token is recognisable (and so
# secret-scanners can flag it). The random part is url-safe base64 of 32 bytes.
TOKEN_PREFIX = "kanban_pat_"
# How much of the raw token to keep as a non-secret display hint (e.g. the UI list
# shows "kanban_pat_ab12…" so a user can tell tokens apart).
PREFIX_DISPLAY_LEN = len(TOKEN_PREFIX) + 4


def hash_token(raw: str) -> str:
    """HMAC-SHA256(AUTH_SECRET, raw) as a 64-char hex digest."""
    return hmac.new(AUTH_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()


def generate_token() -> tuple[str, str, str]:
    """Mint a new PAT → ``(raw, token_prefix, token_hash)``.

    ``raw`` is returned to the caller **once** (never stored); persist only
    ``token_prefix`` (display hint) and ``token_hash``.
    """
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:PREFIX_DISPLAY_LEN], hash_token(raw)
