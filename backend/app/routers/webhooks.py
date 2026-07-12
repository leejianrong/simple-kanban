"""GitHub webhook receiver (KAN-42) — foundation for auto-sync.

A single endpoint GitHub POSTs to. Its authentication is the **HMAC-SHA256
signature** over the raw request body (shared secret ``WEBHOOK_SECRET``), *not*
the cookie/PAT board authz the rest of ``/api/v1`` uses: webhooks come from
GitHub, not a logged-in user, so this route deliberately does **not** depend on
``get_principal``/``authorize_board`` (ADR 0013). It stays standalone.

Scope of this card is **receive + verify + route only** (API-first, ADR 0005):
verify the signature, parse the ``X-GitHub-Event`` type + body, dispatch to a
per-event handler that logs a structured summary, and ack with 200. There is
**no card mutation, no DB write, no model/migration change** — the event-mapping
card builds on this.

Verification policy:
- ``WEBHOOK_SECRET`` unset → **503** (the receiver is not configured; we never
  skip verification silently).
- Missing / malformed / mismatched ``X-Hub-Signature-256`` → **401**.
- Unknown event types are acknowledged (**200**) and ignored.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request, status

logger = logging.getLogger("app.webhooks.github")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Event types this receiver routes on. Anything else is acked (200) and ignored.
HANDLED_EVENTS = {"pull_request", "check_suite", "status"}


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Constant-time-compare the ``sha256=<hex>`` signature GitHub sends.

    GitHub signs the **raw** request body with HMAC-SHA256 keyed on the shared
    secret and sends it as ``X-Hub-Signature-256: sha256=<hexdigest>``.
    """
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


# --- per-event handlers ------------------------------------------------------
# For THIS card each handler only logs a structured summary of the fields a
# later card will map onto board actions. No side effects beyond logging.


def _handle_pull_request(payload: dict) -> None:
    pr = payload.get("pull_request") or {}
    logger.info(
        "webhook pull_request action=%s number=%s state=%s merged=%s title=%r",
        payload.get("action"),
        payload.get("number"),
        pr.get("state"),
        pr.get("merged"),
        pr.get("title"),
    )


def _handle_check_suite(payload: dict) -> None:
    suite = payload.get("check_suite") or {}
    logger.info(
        "webhook check_suite action=%s status=%s conclusion=%s head_sha=%s",
        payload.get("action"),
        suite.get("status"),
        suite.get("conclusion"),
        suite.get("head_sha"),
    )


def _handle_status(payload: dict) -> None:
    logger.info(
        "webhook status state=%s sha=%s context=%r",
        payload.get("state"),
        payload.get("sha"),
        payload.get("context"),
    )


_DISPATCH = {
    "pull_request": _handle_pull_request,
    "check_suite": _handle_check_suite,
    "status": _handle_status,
}


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, object]:
    secret = os.environ.get("WEBHOOK_SECRET")
    if not secret:
        # Misconfiguration, not a client auth failure — never skip verification.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook receiver is not configured (WEBHOOK_SECRET unset)",
        )

    raw = await request.body()
    if not verify_signature(secret, raw, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing signature",
        )

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON",
        ) from exc

    event = x_github_event or ""
    handler = _DISPATCH.get(event)
    if handler is not None:
        handler(payload)
        return {"status": "ok", "event": event, "handled": True}

    logger.info("webhook ignored unknown event=%r", event)
    return {"status": "ok", "event": event, "handled": False}
