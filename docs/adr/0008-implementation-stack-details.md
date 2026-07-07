# ADR 0008 — Implementation stack details

- **Status:** Accepted
- **Date:** 2026-07-07
- **Context source:** decisions made while detailing Shape A (SHAPING.md §C7) and breadboarding.

## Context

ADR 0001 fixed the high-level stack (Svelte 5/Vite 8, FastAPI, PostgreSQL). Detailing the shape
surfaced several lower-level implementation choices that should be recorded so the build is
unambiguous and consistent with the "simplest thing suited to the MVP" principle.

## Decision

- **Backend runtime:** Python 3.12; dependencies managed with **`uv`**.
- **ORM/driver:** **Synchronous** SQLAlchemy 2.0 with the **`psycopg` (v3)** driver — no async, for
  MVP simplicity (FastAPI runs sync endpoints in a threadpool; ample for this scale).
- **Column field storage:** store `column` as a **`varchar` + CHECK constraint** with app-level
  (Pydantic `Enum`) validation, **not** a native PostgreSQL `ENUM` type — so adding column values
  later needs no `ALTER TYPE` migration.
- **Frontend runtime:** Node 20+; package manager **`npm`**.
- **Drag & drop:** **`svelte-dnd-action`**, with **native HTML5 drag events as a fallback** if any
  Svelte 5 compatibility issue arises.
- **Local dev networking:** the Vite dev server **proxies `/api` → the FastAPI backend**, so dev
  mirrors the same-origin production setup and needs no CORS (consistent with ADR 0003).

## Consequences

- **Positive:** Concrete, low-friction toolchain; sync ORM keeps request code simple to read and
  test; `varchar`+CHECK keeps the column set cheaply extensible; `uv`/`npm` are fast and standard.
- **Negative:** Sync SQLAlchemy caps per-process concurrency (fine at MVP scale; revisit with async
  + `asyncpg` if throughput ever matters). `svelte-dnd-action` is a third-party dependency — the
  HTML5 fallback bounds that risk.
- These are implementation details beneath the product decisions; they can evolve without changing
  the domain model (ADR 0006) or the API contract.
