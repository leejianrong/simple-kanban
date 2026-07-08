---
shaping: true
---

# P3 Spike — `/api` → `/api/v1` versioning migration

Investigation for Milestone 2, Shape A, part **P3** (see `SHAPING.md`). Resolves the ⚠️
flag: *how do we introduce a versioned API without breaking the SPA client or the existing
pytest/e2e suites?*

## Context

R4.1 wants a versioned API so future contract changes don't break clients (notably the
coming MCP server). Today everything lives under `/api/cards` (the cards router) plus an
unversioned `/api/health`. Before external clients depend on the contract, we want a
canonical `/api/v1/...`.

## Goal

Describe the concrete, lowest-risk steps to serve the card API under `/api/v1` while
keeping the SPA and both test suites green.

## Findings (investigated in code)

| # | Question | Answer |
|---|----------|--------|
| **P3-Q1** | Where is the API prefix defined? | One place: `backend/app/routers/cards.py` → `APIRouter(prefix="/api/cards")`. `/api/health` is a separate route on the app in `main.py` (infra, not a versioned resource). |
| **P3-Q2** | Can FastAPI serve the same routes under two prefixes? | Yes. Set the router `prefix="/cards"` and call `app.include_router(cards.router, prefix="/api/v1")` **and** `app.include_router(cards.router, prefix="/api")`. Both mounts hit identical handlers. |
| **P3-Q3** | Does the SPA catch-all interfere? | No. `main.py` registers routers **before** the `/{full_path:path}` catch-all, so `/api/v1/cards` matches the router and wins. (Unknown `/api/v1/xyz` still falls to `index.html` rather than 404 — a pre-existing quirk, not introduced here.) |
| **P3-Q4** | Does the Vite dev proxy need changes? | No. `vite.config.ts` proxies `/api` → backend; `/api/v1` is a subpath, already covered. Prod is same-origin, also fine. |
| **P3-Q5** | How many client/test references move? | SPA `frontend/src/lib/api.ts`: **5** `fetch` calls. e2e: **3** (`helpers.ts` ×2 via `APIRequestContext`, `smoke.spec.ts` route glob `**/api/cards/*/move`). Backend tests: **~61** `/api/cards…` string literals across `test_cards.py`, `test_card_crud.py`, `test_move.py`, `test_seed.py`. |
| **P3-Q6** | Does auth (P2) care which prefix? | No — both prefixes route through the same handlers, so the write-guard dependency applies to `/api/v1/*` and the `/api/*` alias identically. |
| **P3-Q7** | Is `/api` a real frozen version or an alias? | An **alias to the current version**, not a frozen v0. Both point at the same handlers, so changing them changes both. Real version-freezing happens later when we add `/api/v2` and stop touching `/api/v1`. That's fine: no external client is on `/api` today except our own SPA/tests, which we update in lockstep. |

## Recommended approach

**Dual-mount, migrate the real client, keep a temporary alias for the tests.**

1. **Backend:** change the router to `prefix="/cards"`; in `main.py` include it twice —
   `prefix="/api/v1"` (canonical) and `prefix="/api"` (compat alias). Hide the alias from
   OpenAPI (`include_in_schema=False` on the second include) so `/docs` shows only v1.
   `/api/health` stays as-is.
2. **SPA:** point `api.ts`'s 5 calls at `/api/v1/cards…` (define a `const API = "/api/v1"`
   base to avoid repetition). The SPA now rides the versioned path.
3. **e2e:** update the 3 refs to `/api/v1` (helpers baseURL calls + the smoke route glob).
4. **Backend tests:** **leave the ~61 literals on `/api/`** for now — they validate the
   same handlers through the alias, so no risky sweep. Add a small `test_versioning.py`:
   asserts `/api/v1/cards` works **and** the `/api/cards` alias still works (documents both).
5. **Later (out of this slice):** once we're happy, sweep the tests to `/api/v1` and drop
   the `/api` alias. Tracked, not now.

### Why not the alternatives
- **Full sweep now** (move everything, no alias): cleanest end-state but churns ~61 test
  literals across a contributor's files in one PR — higher risk of a missed reference, more
  merge surface. Against the lean appetite (R8).
- **`/api` → `/api/v1` 308 redirect**: adds redirect-following edge cases for POST/PATCH/
  DELETE bodies (incl. `/move`) across TestClient / Playwright / httpx. More moving parts
  than a dual-mount for no real gain.

## Acceptance

Complete — we can describe exactly how `/api/v1` is served (dual-mount via two
`include_router` calls on a re-prefixed router), what moves (5 SPA + 3 e2e refs, tests stay
on the alias + 1 new versioning test), and why nothing breaks (identical handlers, catch-all
order unaffected, proxy already covers the subpath). **P3's ⚠️ flag is resolved.**
