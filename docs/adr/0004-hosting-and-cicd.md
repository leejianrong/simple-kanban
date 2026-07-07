# ADR 0004 — Hosting on Fly.io + Neon, CI/CD via GitHub Actions

- **Status:** Accepted
- **Date:** 2026-07-07

## Context

The app must be deployable somewhere others can use it, at free or low cost. The owner previously
tried DigitalOcean. With PostgreSQL now the database (ADR 0002), we need a host for the app
container and a host for Postgres. Constraints: cheap/free, simple, and a clean path to grow.

## Decision

- **App:** Deploy the single Docker artifact (ADR 0003) to **Fly.io** (good Docker DX, free
  allowance, simple `fly deploy`).
- **Database:** Use **Neon** managed serverless PostgreSQL (generous free tier, scales to zero at
  low usage, connection pooling). The app connects via `DATABASE_URL`.
- **CI/CD:** **GitHub Actions**:
  - On pull request: run backend `pytest` and frontend build + lint.
  - On merge to `main`: build the image and `fly deploy` to production.
  - Single `prod` environment for the MVP. `FLY_API_TOKEN` stored as a GitHub secret.

## Consequences

- **Positive:** Both tiers have real free plans; Neon decouples the DB from the app host, so
  scaling the app or swapping hosts later doesn't touch the database. Fly.io Docker deploys keep
  local/prod parity.
- **Negative:** Two vendors to hold accounts with (Fly + Neon) rather than one all-in-one PaaS.
  Free tiers have limits and can change; revisit if usage grows.
- **Alternatives considered:** Render (free web service spins down when idle; free Postgres is
  time-limited), Railway (simple, small monthly credit), a single Hetzner VPS (cheapest at scale
  but most ops). Fly + Neon chosen as the best free/simple/low-debt balance.
