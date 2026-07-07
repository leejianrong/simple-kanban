# ADR 0001 — Tech stack and monorepo layout

- **Status:** Accepted
- **Date:** 2026-07-07

## Context

We are building an MVP Kanban web app that must be quickly deployable and demoable. REQS.md fixes
several stack choices: Svelte 5 + Vite 8 frontend, FastAPI backend. We need a persistent database
and a repo structure that keeps a small team (and future AI agents) productive.

## Decision

- **Frontend:** Svelte 5 + Vite 8, built as a static SPA.
- **Backend:** FastAPI + Pydantic, with SQLAlchemy as the ORM.
- **Database:** PostgreSQL (see ADR 0002).
- **Repo:** Single monorepo with `/frontend` and `/backend` top-level directories.

## Consequences

- One repository to clone, version, and CI. Frontend and backend evolve together.
- SQLAlchemy + Pydantic is the conventional, well-documented FastAPI pairing — low friction.
- Svelte 5's runes + Vite 8 are current; team must be comfortable with Svelte 5 idioms.
- Coupling FE/BE releases is acceptable for an MVP; can split later if needed.
