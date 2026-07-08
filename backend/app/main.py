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

from .routers import cards, epics

app = FastAPI(title="Simple Kanban API", version="0.1.0")

# Dual-mount each router (P3, spike-p3-versioning.md): the canonical versioned
# path /api/v1/... plus a temporary /api alias for clients not yet migrated. Both
# mounts hit identical handlers; the alias is hidden from OpenAPI so /docs shows
# only /api/v1 (+ /api/health). Dropping the alias is a later chore.
app.include_router(cards.router, prefix="/api/v1")
app.include_router(epics.router, prefix="/api/v1")
app.include_router(cards.router, prefix="/api", include_in_schema=False)
app.include_router(epics.router, prefix="/api", include_in_schema=False)


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
