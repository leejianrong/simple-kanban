# ADR 0005 — API-first design, MCP/CLI-ready but integrations deferred

- **Status:** Accepted
- **Date:** 2026-07-07

## Context

A core motivation in REQS.md is future extensibility: an MCP server, a CLI, and LLM agents should
be able to perform actions on the Kanban app. We must not build those now (MVP scope), but we also
must not paint ourselves into a corner that makes them expensive later.

## Decision

Design **API-first**: every user-facing action is a REST + JSON endpoint under `/api/*`, fully
described by FastAPI's auto-generated **OpenAPI** schema (`/docs`). The Svelte UI is treated as
just the first API client and is given no privileged, non-API pathway. No MCP server, CLI, or agent
code is built in the MVP.

## Consequences

- **Positive:** A later MCP server or CLI is a thin adapter over an already-complete, documented
  API — no backend rework. Clear separation makes the UI and future clients interchangeable.
- **Negative:** Slightly more discipline now (no shortcuts that bypass the API from the UI).
- Endpoint naming and payloads should stay explicit and stable-feeling, since future agent tools
  will bind to them. Dedicated action endpoints (e.g. `move`) are preferred for clear tool
  semantics (see ADR 0006).
