"""Thin synchronous httpx client over the Simple Kanban REST API (`/api/v1`).

One method per MCP tool. Keeps the transport injectable so unit tests can drive
every method against an ``httpx.MockTransport`` with no real server. Non-2xx
responses become a ``KanbanApiError`` carrying the API's own ``detail`` string,
so the agent sees a useful message (e.g. a 401 when a token is required).
"""
from __future__ import annotations

from typing import Any

import httpx

DEFAULT_TIMEOUT = 10.0

# Agent-facing hints for the auth failures V10 cares about (ADR 0015): a bad/
# expired token vs. a board the caller's user doesn't own. The raw server detail
# is preserved on ``.detail``; the hint just frames it usefully for the agent.
_FRIENDLY_HINTS = {
    401: "bad or expired token — set KANBAN_TOKEN to a valid PAT (create one in the Tokens UI)",
    403: "that board isn't yours — call list_boards to see the boards you can use",
}


class KanbanApiError(RuntimeError):
    """A non-2xx response from the Kanban API (status + server-provided detail)."""

    def __init__(self, status_code: int, detail: str) -> None:
        hint = _FRIENDLY_HINTS.get(status_code)
        message = f"{status_code}: {hint} ({detail})" if hint else f"{status_code}: {detail}"
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _detail(response: httpx.Response) -> str:
    """Best-effort extraction of the API's ``{"detail": ...}`` error message."""
    try:
        body = response.json()
    except ValueError:
        return response.text or f"request failed ({response.status_code})"
    if isinstance(body, dict) and body.get("detail") is not None:
        detail = body["detail"]
        return detail if isinstance(detail, str) else str(detail)
    return f"request failed ({response.status_code})"


def _clean(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop unset (None) fields so we send only what the caller provided."""
    return {key: value for key, value in fields.items() if value is not None}


class KanbanClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/v1",
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "KanbanClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        if not response.is_success:
            raise KanbanApiError(response.status_code, _detail(response))
        return response

    # --- boards (discovery — V10) -------------------------------------------

    def list_boards(self) -> dict[str, Any]:
        """List the boards the caller's user owns (owner-scoped by the API)."""
        return {"boards": self._request("GET", "/boards").json()}

    def create_board(self, name: str) -> dict[str, Any]:
        """Create a board owned by the caller's user."""
        return self._request("POST", "/boards", json={"name": name}).json()

    def update_board(self, board_id: int, *, name: str | None = None) -> dict[str, Any]:
        payload = _clean({"name": name})
        return self._request("PATCH", f"/boards/{board_id}", json=payload).json()

    def get_board(self, board_id: int) -> dict[str, Any]:
        return self._request("GET", f"/boards/{board_id}").json()

    def delete_board(self, board_id: int) -> dict[str, Any]:
        # 204 No Content — no body to parse.
        self._request("DELETE", f"/boards/{board_id}")
        return {"deleted": board_id}

    # --- reads --------------------------------------------------------------

    def list_cards(
        self,
        *,
        board_id: int | None = None,
        column: str | None = None,
        epic_id: int | None = None,
        updated_since: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params = _clean(
            {
                "board_id": board_id,
                "column": column,
                "epic_id": epic_id,
                "updated_since": updated_since,
                "limit": limit,
                "cursor": cursor,
            }
        )
        response = self._request("GET", "/cards", params=params)
        result: dict[str, Any] = {"cards": response.json()}
        # The keyset pagination cursor for the next page rides a header (V3).
        next_cursor = response.headers.get("X-Next-Cursor")
        if next_cursor:
            result["next_cursor"] = next_cursor
        return result

    def list_epics(self, *, board_id: int | None = None) -> dict[str, Any]:
        params = _clean({"board_id": board_id})
        return {"epics": self._request("GET", "/epics", params=params).json()}

    def get_card(self, card_id: int) -> dict[str, Any]:
        return self._request("GET", f"/cards/{card_id}").json()

    def get_epic(self, epic_id: int) -> dict[str, Any]:
        return self._request("GET", f"/epics/{epic_id}").json()

    # --- writes -------------------------------------------------------------

    def create_card(
        self,
        title: str,
        *,
        board_id: int | None = None,
        description: str | None = None,
        column: str | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        epic_id: int | None = None,
    ) -> dict[str, Any]:
        payload = _clean(
            {
                "board_id": board_id,
                "title": title,
                "description": description,
                "column": column,
                "story_points": story_points,
                "assignee": assignee,
                "epic_id": epic_id,
            }
        )
        return self._request("POST", "/cards", json=payload).json()

    def create_epic(
        self, name: str, *, board_id: int | None = None, description: str | None = None
    ) -> dict[str, Any]:
        payload = _clean({"board_id": board_id, "name": name, "description": description})
        return self._request("POST", "/epics", json=payload).json()

    def update_epic(
        self, epic_id: int, *, name: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        payload = _clean({"name": name, "description": description})
        return self._request("PATCH", f"/epics/{epic_id}", json=payload).json()

    def delete_epic(self, epic_id: int) -> dict[str, Any]:
        # 204 No Content — no body to parse.
        self._request("DELETE", f"/epics/{epic_id}")
        return {"deleted": epic_id}

    def update_card(
        self,
        card_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        epic_id: int | None = None,
    ) -> dict[str, Any]:
        payload = _clean(
            {
                "title": title,
                "description": description,
                "story_points": story_points,
                "assignee": assignee,
                "epic_id": epic_id,
            }
        )
        return self._request("PATCH", f"/cards/{card_id}", json=payload).json()

    def move_card(
        self, card_id: int, column: str, *, position: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"column": column}
        if position is not None:
            payload["position"] = position
        return self._request("POST", f"/cards/{card_id}/move", json=payload).json()

    def delete_card(self, card_id: int) -> dict[str, Any]:
        # 204 No Content — no body to parse.
        self._request("DELETE", f"/cards/{card_id}")
        return {"deleted": card_id}
