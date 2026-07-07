# ADR 0003 — Single-artifact deployment (FastAPI serves the built SPA)

- **Status:** Accepted
- **Date:** 2026-07-07

## Context

We have a Svelte SPA and a FastAPI backend. They can be deployed separately (static host + API
host) or bundled. Separate hosting introduces CORS configuration, two deploy pipelines, and two
origins to reason about. For a simple MVP we want the fewest moving parts.

## Decision

Build the Svelte app to static assets and have **FastAPI serve those static files** alongside the
`/api/*` routes. The result is a **single deployable artifact** (one Docker image, one origin).

## Consequences

- **Positive:** No CORS. One thing to deploy, one URL to demo. Simplest possible topology.
- **Negative:** FE and BE scale together and release together (acceptable for MVP; see ADR 0001).
- The Dockerfile is multi-stage: build the Svelte bundle, then copy it into the Python image which
  FastAPI serves as static + SPA-fallback routes.
- If we later need an independent CDN-hosted frontend, the API is already cleanly separated under
  `/api/*`, so the split is low-cost.
