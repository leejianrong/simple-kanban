"""Bearer-token plumbing for the transitional **service** principal (M2 V4 → M3 V8).

Originally (V4, ADR 0010) this module guarded *writes* with an optional
``API_TOKENS`` bearer: unset → writes open. **V8 (ADR 0013) changes that** — the
whole ``/api/v1`` surface is now authorization-required (owner-gated), so the
old "open when unset" write-guard is gone. What survives here is just the token
*parsing*: a valid ``API_TOKENS`` bearer resolves to a **SERVICE** principal that
bypasses the per-board owner check (see :mod:`app.authz`).

This is a deliberate, documented **transitional** bypass so the MCP server (which
still authenticates with the shared ``API_TOKENS`` bearer, not a per-user token)
keeps working during the V8→V9 window. **V9 retires ``API_TOKENS``** in favour of
per-user hashed personal access tokens that resolve to a real ``User`` principal.

The token set is read from the environment per request (not cached), so a
deployment can rotate ``API_TOKENS`` without a rebuild and tests can toggle it.
"""
from __future__ import annotations

import os

from fastapi.security import HTTPBearer

# auto_error=False: the presence of a token is optional at the scheme level; the
# principal resolver (app.authz) decides whether the *request* is authorized
# (cookie session OR a valid service token), returning 401 itself otherwise.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Agent service token (from API_TOKENS) — transitional, retired in V9.",
)


def configured_tokens() -> set[str]:
    """The set of currently-valid service tokens, parsed from ``API_TOKENS``
    (comma-separated). Empty (the default) means no service bypass is available —
    every request must then carry a valid human cookie session."""
    raw = os.environ.get("API_TOKENS", "")
    return {token.strip() for token in raw.split(",") if token.strip()}
