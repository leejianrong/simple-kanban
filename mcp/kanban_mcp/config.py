"""Runtime config for the MCP server, read from the environment.

- ``KANBAN_API_URL`` — base URL of the Kanban API (default the local dev backend).
  The ``/api/v1`` prefix is added by the client, so give just the origin.
- ``KANBAN_TOKEN`` — bearer token for writes. Optional: only needed when the
  target has ``API_TOKENS`` set (ADR 0010). Empty/unset → no Authorization header.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_API_URL = "http://localhost:8000"


@dataclass(frozen=True)
class Config:
    api_url: str
    token: str | None


def load_config() -> Config:
    api_url = os.environ.get("KANBAN_API_URL", DEFAULT_API_URL).strip() or DEFAULT_API_URL
    # Treat empty string the same as unset (a common .mcp.json placeholder).
    token = os.environ.get("KANBAN_TOKEN", "").strip() or None
    return Config(api_url=api_url, token=token)
