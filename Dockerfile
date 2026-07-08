# syntax=docker/dockerfile:1
# Single deployable artifact (ADR 0003): build the Svelte SPA, then serve it plus
# the API from one FastAPI/uvicorn process. Also used by docker-compose for local
# full-stack runs.

# ---- Stage 1: build the Svelte SPA ----
FROM node:22-slim AS frontend
WORKDIR /frontend
# Install deps against the lockfile first for better layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # -> /frontend/dist

# ---- Stage 2: Python runtime serving API + built SPA ----
FROM python:3.12-slim AS runtime
# uv for fast, reproducible dependency installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    STATIC_DIR=/app/static \
    PATH="/app/.venv/bin:$PATH"

# Install backend deps first (cached unless pyproject/lock change).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# Backend source (alembic.ini, alembic/, app/).
COPY backend/ ./
# Built SPA -> the directory FastAPI serves (main.py reads STATIC_DIR).
COPY --from=frontend /frontend/dist ./static

EXPOSE 8000
# Apply migrations (incl. future seed) then start the server. Migrations are
# idempotent, so this is safe on every start.
#
# --proxy-headers + --forwarded-allow-ips=* make uvicorn honour Fly's
# X-Forwarded-Proto/Host, so request URLs are built as https://<host> behind the
# TLS-terminating edge proxy. This is required for the GitHub OAuth callback
# (M3 V6, ADR 0011): without it the generated redirect_uri is http:// and GitHub
# rejects the mismatch. Trusting all forwarded IPs is safe here because only the
# Fly proxy can reach the container's internal port.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
