# ADR 0002 — PostgreSQL + Alembic from day one

- **Status:** Accepted (supersedes the initial SQLite idea in REQS.md)
- **Date:** 2026-07-07

## Context

REQS.md initially proposed SQLite for the MVP, "may consider Postgres in the future." On
reflection, the future migration (SQLite → Postgres) is a well-known source of technical debt:
SQL dialect differences, type affinity surprises, concurrency model differences, and the pain of
retrofitting a migration history onto an already-populated database. We would rather pay a tiny
upfront cost than a larger later one.

## Decision

Use **PostgreSQL** as the database from the very first commit, and manage all schema changes with
**Alembic** migrations from day one (no `create_all`-then-migrate-later phase).

## Consequences

- **Positive:** No future DB migration project. Production parity in dev via a local Postgres
  (Docker). Alembic gives a clean, reviewable schema history. Postgres features (sequences for
  ticket numbers, real constraints) are available immediately.
- **Negative / cost:** Slightly heavier local dev setup than a single SQLite file — mitigated by a
  `docker-compose` Postgres for local development. Every schema change requires an Alembic
  revision (this is the discipline we want anyway).
- Drives the hosting choice toward a managed Postgres (see ADR 0004).
