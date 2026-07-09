"""Runtime config for the ``kan`` CLI, read from the environment.

Mirrors the MCP server's config (``kanban_mcp.config``) — the two thin adapters
own their own env parsing while sharing the client. Vars:

- ``KANBAN_API_URL`` — base URL of the Kanban API (default the local dev backend).
  The ``/api/v1`` prefix is added by the client, so give just the origin.
- ``KANBAN_TOKEN`` — bearer token. Since M3 V8 (ADR 0013) the whole ``/api/v1``
  surface is auth-required, so this is **required**: a personal access token
  (``kanban_pat_…``, created in the SPA Tokens UI, V9/ADR 0014). Empty/unset is a
  clean CLI error before any request is made.
- ``KANBAN_BOARD_ID`` — optional default board (an integer id) for board-scoped
  commands (``list``/``create``) when they omit ``--board``. Unset → the API's own
  fallback (list = all your boards; create = your earliest board).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_API_URL = "http://localhost:8000"


class ConfigError(Exception):
    """Raised when the environment is missing something the CLI needs."""


@dataclass(frozen=True)
class Config:
    api_url: str
    token: str
    board_id: int | None


def load_config() -> Config:
    """Read config from the environment. Raises ``ConfigError`` (mapped to a clean
    stderr message + non-zero exit by the CLI) when ``KANBAN_TOKEN`` is missing or
    ``KANBAN_BOARD_ID`` is not an integer."""
    api_url = os.environ.get("KANBAN_API_URL", DEFAULT_API_URL).strip() or DEFAULT_API_URL
    token = os.environ.get("KANBAN_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "KANBAN_TOKEN is required (a personal access token 'kanban_pat_…'; "
            "create one in the Tokens UI). The /api/v1 API is auth-required."
        )
    board_id = _parse_board_id(os.environ.get("KANBAN_BOARD_ID", ""))
    return Config(api_url=api_url, token=token, board_id=board_id)


def _parse_board_id(raw: str) -> int | None:
    """Parse the optional default board id; empty → None, non-integer → a clear error."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"KANBAN_BOARD_ID must be an integer, got {raw!r}") from exc
