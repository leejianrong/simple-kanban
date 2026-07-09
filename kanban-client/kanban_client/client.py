"""Thin synchronous httpx client over the Simple Kanban REST API (`/api/v1`).

Shared single source of truth for talking to the API: the MCP server and the
CLI both import ``KanbanClient`` from here so the two thin adapters never drift
(DRY; API-first, ADR 0005). One method per API endpoint. The transport is
injectable so unit tests can drive every method against an ``httpx.MockTransport``
with no real server. Non-2xx responses become a ``KanbanApiError`` carrying the
API's own ``detail`` string, so the caller sees a useful message (e.g. a 401 when
a token is required).

Config (base_url / token / timeout / connect_timeout / retry_backoff) is passed
in by the caller — this module reads no environment, so each adapter (MCP, CLI)
owns its own env parsing.

Cold-start resilience (KAN-25): the Fly free tier scales to zero, so the first
request after idle fails while the machine wakes. The request path uses a
generous read timeout plus a single automatic retry to ride that out; see
``KanbanClient._send_with_retry`` for the exact policy.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

# The Fly free tier scales the app to zero, so the FIRST request after idle does
# not just come back slow — the machine takes ~30-40s to wake and the request
# fails mid-flight (connect/handshake error or a read timeout) before it serves
# 200s normally. So we ride it out with a generous READ timeout and a short
# CONNECT timeout (a dead host should fail fast; a waking one just reads slowly),
# plus a single automatic retry (see ``_request``). Read timeout is deliberately
# > the observed ~30s cold-start window. ``timeout`` is caller-configurable.
DEFAULT_TIMEOUT = 35.0
DEFAULT_CONNECT_TIMEOUT = 5.0

# Fixed backoff before the single cold-start retry, giving the machine a moment
# to finish waking. One retry, not a loop — caller-configurable (tests set 0).
DEFAULT_RETRY_BACKOFF = 1.0

# Transport failures where the request provably never reached the server (no
# connection / broken handshake). Safe to retry for ANY method — nothing was
# applied server-side. ``RemoteProtocolError`` is the raw symptom of Fly's
# TLS "UNEXPECTED_EOF" mid-handshake while the machine wakes.
_RETRY_ALWAYS_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError)

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
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._retry_backoff = retry_backoff
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/v1",
            headers=headers,
            # Generous read/write/pool timeout to ride out a cold start, but a
            # short connect timeout so a genuinely-down host fails fast.
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "KanbanClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._send_with_retry(method, path, **kwargs)
        if not response.is_success:
            # An HTTP error *response* (4xx/5xx) is not a cold start — never
            # retried; the existing error mapping is unchanged.
            raise KanbanApiError(response.status_code, _detail(response))
        return response

    def _send_with_retry(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send once, with a single cold-start retry on transient transport errors.

        A scale-to-zero cold start surfaces as a transport-level exception, not an
        error response, so the retry lives here and never fires on 4xx/5xx:

        - connection/handshake errors (``_RETRY_ALWAYS_ERRORS``) mean the request
          never reached the server, so retry is safe for **any** method;
        - a ``ReadTimeout`` means the request *may* have been applied server-side,
          so we only retry **idempotent** ``GET``s. This app is last-write-wins
          with no idempotency keys (ADR 0007), so we never risk a double
          POST/PATCH/DELETE.

        Exactly one retry — if the retry also fails, the exception propagates.
        """
        try:
            return self._client.request(method, path, **kwargs)
        except _RETRY_ALWAYS_ERRORS:
            return self._retry(method, path, **kwargs)
        except httpx.ReadTimeout:
            if method.upper() != "GET":
                raise
            return self._retry(method, path, **kwargs)

    def _retry(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._retry_backoff > 0:
            time.sleep(self._retry_backoff)
        return self._client.request(method, path, **kwargs)

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

    # --- health / warmup ----------------------------------------------------

    def health(self) -> dict[str, Any]:
        """GET the **unversioned** ``/api/health`` (it lives at the origin, not
        under ``/api/v1``). Rides a cold start via the shared retry/timeout and
        raises ``KanbanApiError`` on a non-2xx response; returns the parsed body
        (``{"status": "ok"}``)."""
        # base_url is ``<origin>/api/v1/``; joining an absolute path swaps the
        # whole path (RFC 3986) so we reach ``<origin>/api/health`` without the
        # ``/api/v1`` prefix and without hard-coding the origin. The result is a
        # fully-qualified URL, so httpx sends it as-is (no base_url merge).
        url = self._client.base_url.join("/api/health")
        return self._request("GET", str(url)).json()

    def warmup(self) -> dict[str, Any]:
        """Wake a scaled-to-zero server by pinging ``/api/health``.

        Rides the cold start via the shared retry/timeout (an idempotent GET is
        retried once), but **does not throw** on a slow wake: a still-waking
        server (transport error/timeout) returns ``{"status": "waking", ...}`` and
        any other API error returns ``{"status": "error", ...}``, so an agent gets
        a clear result to act on rather than an exception. A healthy server returns
        ``{"status": "ok", "health": {...}}``.
        """
        try:
            body = self.health()
        except httpx.TransportError as exc:
            return {
                "status": "waking",
                "detail": f"server not ready yet ({exc.__class__.__name__}); retry shortly",
            }
        except KanbanApiError as exc:
            return {"status": "error", "detail": str(exc)}
        return {"status": "ok", "health": body}

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

    def create_cards(self, cards: list[dict[str, Any]]) -> dict[str, Any]:
        """Batch-create stories: loop ``create_card`` for each dict in ``cards``
        (a warm-connection convenience for filing a whole epic's worth of stories
        in one call — the shared client's cold-start retry only bites the first
        request). Each dict takes the same fields as ``create_card`` (``title``
        required; optional ``board_id``/``description``/``column``/``story_points``/
        ``assignee``/``epic_id``). Returns ``{"created": [<card>, ...]}``.

        **Fail-fast, not atomic:** on the first error the exception propagates and
        cards created before it **stay created** (no rollback — there is no batch
        endpoint; ADR 0007 last-write-wins). Order is preserved.
        """
        created = [self.create_card(**card) for card in cards]
        return {"created": created}

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

    def claim_card(self, card_id: int, assignee: str) -> dict[str, Any]:
        """Atomically 'pull' a card: move it to ``in_progress`` **and** set its
        ``assignee`` in one call. Composes the two existing endpoints — first
        ``move_card`` (column change), then ``update_card`` (field edit), since the
        move/edit split is deliberate (ADR 0005). Returns the resulting card (the
        PATCH response, reflecting both changes). Not transactional: if the PATCH
        fails after the move, the card stays moved but unassigned.
        """
        self.move_card(card_id, "in_progress")
        return self.update_card(card_id, assignee=assignee)

    def delete_card(self, card_id: int) -> dict[str, Any]:
        # 204 No Content — no body to parse.
        self._request("DELETE", f"/cards/{card_id}")
        return {"deleted": card_id}

    # --- card-to-card dependencies (KAN-28 API / KAN-31 adapter) ------------

    def add_dependency(self, card_id: int, blocker_id: int) -> dict[str, Any]:
        """Record that card ``card_id`` is **blocked-by** ``blocker_id`` (insert the
        edge ``blocker_id → card_id``). Returns the now-blocked card with its
        refreshed ``blocked_by`` / ``blocks`` arrays."""
        return self._request(
            "POST", f"/cards/{card_id}/dependencies", json={"blocker_id": blocker_id}
        ).json()

    def remove_dependency(self, card_id: int, blocker_id: int) -> dict[str, Any]:
        """Remove the ``blocker_id → card_id`` edge (card ``card_id`` is no longer
        blocked-by ``blocker_id``). Returns the card with refreshed dependency
        arrays (the DELETE responds with the card body, not 204)."""
        return self._request(
            "DELETE", f"/cards/{card_id}/dependencies/{blocker_id}"
        ).json()

    def list_dependencies(self, card_id: int) -> dict[str, Any]:
        """List a card's dependency edges. There is no dedicated endpoint — the
        API surfaces ``blocked_by`` / ``blocks`` on the card itself — so this reads
        the card (``GET /cards/{id}``) and shapes just its dependency arrays:
        ``{"card_id": id, "blocked_by": [...], "blocks": [...]}``.
        ``blocked_by`` = ids that block this card; ``blocks`` = ids it blocks."""
        card = self.get_card(card_id)
        return {
            "card_id": card_id,
            "blocked_by": card.get("blocked_by", []),
            "blocks": card.get("blocks", []),
        }
