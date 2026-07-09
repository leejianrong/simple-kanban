"""FastAPI application entrypoint (SHAPING §Static + SPA, BREADBOARD §6).

Registration order matters: the API router and FastAPI's own /docs are mounted
first, then — only if a built SPA exists — static assets and a catch-all fallback
that returns index.html for any non-/api, non-/docs path (client-side routing).

In local dev the SPA is served by Vite (which proxies /api here), so ``STATIC_DIR``
usually does not exist and the fallback is simply not registered.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import boards, cards, epics, tokens
from .users import register_auth_routes

app = FastAPI(title="Simple Kanban API", version="0.1.0")

# Mount each router under the canonical versioned prefix /api/v1/... (P3,
# spike-p3-versioning.md). The temporary /api compat alias that eased the V2
# migration has been dropped now that all clients (SPA, e2e, backend tests) ride
# /api/v1. /api/health stays unversioned (infra, not a versioned resource).
app.include_router(boards.router, prefix="/api/v1")
app.include_router(cards.router, prefix="/api/v1")
app.include_router(epics.router, prefix="/api/v1")
app.include_router(tokens.router, prefix="/api/v1")  # M3 V9 (ADR 0014): agent PATs

# Human auth (M3 V6, ADR 0011): /auth/* + /users/*, unversioned like /api/health
# (session/identity plumbing, not versioned API resources). The GitHub OAuth
# routes register only when creds are set — see register_auth_routes.
register_auth_routes(app)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# Path to the built Svelte SPA. Overridable via env for the Docker image layout.
STATIC_DIR = Path(
    os.environ.get(
        "STATIC_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"),
    )
)

if STATIC_DIR.is_dir():
    # Serve hashed asset files (JS/CSS/images) built by Vite.
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = STATIC_DIR / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        # Serve a real static file if one exists (e.g. favicon), else index.html
        # so the client-side app boots for any unknown route.
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)
