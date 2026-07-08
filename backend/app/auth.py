"""Optional bearer-token auth on writes (Milestone 2 V4, P2 / R3.1).

Lets non-interactive agents (the coming MCP server) authenticate on mutating
requests without changing anything for the SPA or local dev:

- Valid tokens come from the ``API_TOKENS`` env var (comma-separated).
- **If ``API_TOKENS`` is unset/empty → writes stay open** — the MVP/dev default
  (ADR 0007's no-auth stance) and what keeps the existing write tests green.
- If it is set → mutating routes require ``Authorization: Bearer <token>`` with a
  listed token, else ``401``. **Reads are always open** (the SPA never sends a
  token). Scoped read/write tokens + revocation are explicitly Later (R3.4).

The token set is read from the environment per request (not cached), so a
deployment can rotate ``API_TOKENS`` and tests can toggle it without rebuilding
the app.
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# auto_error=False: we implement the "open when unset" branch ourselves rather
# than let HTTPBearer reject every tokenless request.
_bearer = HTTPBearer(
    auto_error=False,
    description="Agent API token (set only when API_TOKENS is configured).",
)


def _configured_tokens() -> set[str]:
    """The set of currently-valid tokens, parsed from ``API_TOKENS`` (comma-sep).

    Empty (the default) means auth is disabled and writes are open.
    """
    raw = os.environ.get("API_TOKENS", "")
    return {token.strip() for token in raw.split(",") if token.strip()}


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """FastAPI dependency for mutating routes: enforce a bearer token iff one or
    more are configured. A no-op when ``API_TOKENS`` is unset."""
    tokens = _configured_tokens()
    if not tokens:
        return  # auth disabled — writes open
    if credentials is None or credentials.credentials not in tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
