"""Observability: structured request logging + optional error tracking (KAN-172).

Two pieces, both built so dev and the test suite stay quiet and never phone home:

- **Structured JSON logging** — one JSON line per HTTP request on the
  ``kanban.access`` logger: ``method``, ``path``, ``status_code``, ``latency_ms``,
  and ``principal_id`` when the route resolved one (``app.authz.get_principal``
  stashes it on ``request.state``). Level via the ``LOG_LEVEL`` env var (default
  ``INFO``). **Never logs secrets**: only the URL *path* (query string dropped),
  and never headers, cookies, or bearer tokens.
- **Error tracking** — Sentry, initialised **only** when ``SENTRY_DSN`` is set; a
  pure no-op otherwise, so dev and tests (which set no DSN) never report anywhere
  and don't even import the SDK. Mirrors the "GitHub OAuth routes only mount when
  creds are set" pattern in :mod:`app.users`.

The DB-readiness health probe lives in :mod:`app.main` — it needs the sync board
engine (ADR 0008), so it belongs with the app wiring rather than here.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request

ACCESS_LOGGER = "kanban.access"


class JsonLogFormatter(logging.Formatter):
    """Render a ``LogRecord`` as a single-line JSON object.

    Standard fields (``ts``, ``level``, ``logger``, ``msg``) plus an **allow-list**
    of request fields pulled from the record. We deliberately allow-list rather
    than dumping ``record.__dict__`` so a stray secret can never be serialised into
    a log line by accident.
    """

    _REQUEST_FIELDS = ("method", "path", "status_code", "latency_ms", "principal_id")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in self._REQUEST_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Attach a JSON stdout handler to the access logger at ``LOG_LEVEL``.

    Idempotent — replaces its own handler on each call, so re-initialising (e.g.
    under the test client, or a reload) never duplicates lines.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    logger = logging.getLogger(ACCESS_LOGGER)
    logger.setLevel(level)
    logger.handlers = [handler]
    logger.propagate = False


def _principal_id(request: Request) -> str | None:
    """The id of the principal a route resolved for this request, if any.

    ``app.authz.get_principal`` sets ``request.state.principal_id`` when it resolves
    a cookie session or PAT to a user. Infra/unauthenticated routes (health, auth,
    webhooks) never set it, so this returns ``None`` for them — "where available".
    """
    pid = getattr(request.state, "principal_id", None)
    return str(pid) if pid is not None else None


def add_request_logging(app: FastAPI) -> None:
    """Register the HTTP middleware that emits one structured line per request."""
    logger = logging.getLogger(ACCESS_LOGGER)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # pyright: ignore[reportUnusedFunction]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Log the failure (with traceback) before it propagates to Starlette's
            # error handler, so a 500 still leaves an access line + is Sentry-caught.
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "latency_ms": latency_ms,
                    "principal_id": _principal_id(request),
                },
            )
            raise
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request",
            extra={
                "method": request.method,
                # Path only — never the query string (avoids logging any value a
                # client tucks into the URL); headers/cookies/tokens are never read.
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "principal_id": _principal_id(request),
            },
        )
        return response


def init_error_tracking() -> bool:
    """Initialise Sentry error reporting **iff** ``SENTRY_DSN`` is set.

    No-op (returns ``False``, and never imports the SDK) when unset — so dev and
    the test suite report nowhere by default. Returns ``True`` when enabled.

    ``send_default_pii=False`` keeps request headers, cookies, and bearer tokens
    out of every event, so PATs and session cookies are never transmitted.
    """
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        # Off by default; opt in to tracing via env without a code change.
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
    )
    logging.getLogger(ACCESS_LOGGER).info("error tracking enabled")
    return True
