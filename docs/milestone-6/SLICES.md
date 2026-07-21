---
shaping: true
---

# Milestone 6 — Slices ("Harden & Sharpen")

Vertical increments of the [M6 shape](SHAPING.md). Each ends in **observable behaviour** and ships as
its own PR behind CI, matching the M1–M5 cadence.

Numbering continues the **global V-series** (M2 = V1–V5, M3 = V6–V10, M5 = V11–V19; M4 was tracked
directly as EPIC-3…EPIC-17). **M6 is V26–V39.** Every slice that adds a surface includes **API + MCP +
CLI parity** (R6.4) — endpoint first, then the MCP tool + `kan` verb, then any UI.

**Waves.** M6 is larger than prior milestones, so it runs in waves:
- **Wave 1 — Harden (V26–V30):** ships first, before any feature work. The box is live and unguarded.
- **Wave 2 — Sharpen core (V31–V34):** projects + cycles — the milestone is demo-complete after this.
- **Wave 3 — Tail (V35–V39):** command palette + notifications — *Nice-to-have*, demos complete
  without them (as M5 treated V18/V19).

| Slice | What | Part | Wave | Ends in (demo) |
|-------|------|------|:----:|----------------|
| **V26 · Edge + load-shedding** | Cloudflare front + Fly `hard_limit` | H1 | 1 | Fly origin not directly reachable; SPA served from edge; a concurrency flood returns `503`, not a crash |
| **V27 · App rate limiting** | `slowapi`, `429`+`Retry-After` | H2 | 1 | Hammer `/auth` (or writes) past the limit → `429` with `Retry-After`; normal use unaffected |
| **V28 · Payload hardening** | body/string/array caps | H3 | 1 | A 10 MB body and a 10k-item batch are rejected fast (`413`/`422`); normal payloads pass |
| **V29 · Security headers** | HSTS/CSP/nosniff/frame | H4 | 1 | API + SPA responses carry the headers; SPA + `/docs` still load |
| **V30 · DB resilience** | statement + pool timeouts | H5 | 1 | A deliberately slow statement is cancelled at the timeout; a cold-start burst degrades to `429`/`503` not a hang |
| **V31 · Project fields** | `epic.target_date` + `epic.lead` | P1 | 2 | `kan epic update <id> --target-date … --lead …`; fields round-trip via API/MCP/CLI |
| **V32 · Progress rollup + health** | derived % + health | P2 | 2 | An epic shows `60% · at risk` on the Epics page and in the API |
| **V33 · Cycle model + API** | `cycle` + `card.cycle_id` | C1 | 2 | Create a cycle, assign cards, `kan list --cycle <id>` returns them |
| **V34 · Cycle burndown / velocity** | cycle-scoped metrics | C2 | 2 | An active cycle shows a burndown line + committed-vs-completed |
| **V35 · Command palette (⌘K)** *(tail)* | fuzzy command menu | K1 | 3 | ⌘K → "move KAN-x to done" → the card moves |
| **V36 · Keyboard shortcuts** *(tail)* | shortcuts + `?` overlay | K2 | 3 | Navigate columns and move a card with only the keyboard |
| **V37 · Notification store + inbox API** *(tail)* | emit-on-event + API | N1 | 3 | Raise `needs_human` → `kan notify` lists the notification; mark it read |
| **V38 · Signed outbound webhook** *(tail)* | per-board HMAC webhook | N2 | 3 | Point at a request-bin, raise a notification, see the signed `POST` |
| **V39 · Inbox UI + badge** *(tail)* | read-first inbox panel | N3 | 3 | An unread badge appears; opening the Inbox clears it |

> **Status:** planned (0/14). Board cards: **KAN-290…KAN-303** (this file's V26–V39), under the five
> `M6:` epics **EPIC-46…EPIC-50**. The sister-app kickoff is **KAN-304** (human-owned).

---

## Wave 1 — Harden

### V26 · Edge protection + Fly load-shedding (H1)
- **Build:** front the Fly app with Cloudflare (free): DNS proxy on (origin hidden), cache the static
  SPA assets, enable Bot Fight / basic managed WAF rules. Set `http_service.concurrency` with a
  `hard_limit`/`soft_limit` in `fly.toml` so the 256 MB box sheds (`503`) instead of OOMing. Document
  the Cloudflare setup in `docs/guides/edge-hardening.md` (ops runbook; DNS is a human step).
- **Tests:** n/a in CI for the edge (external); `fly.toml` change is config. Verify post-deploy:
  origin host not reachable except via Cloudflare; a `hey`/`ab` burst returns `503` not a crash.
- **Acceptance:** the demo; origin hidden; ops doc landed. Config + docs — deploys.

### V27 · Application rate limiting (H2)
- **Build:** add `slowapi` (in-memory limiter; single machine). Apply limits to: `login` +
  `/auth/github/callback`, all `/api/v1` writes + `dispatch` + `POST /tokens`, `GET /cards?q=` +
  `/metrics`, `POST /webhooks/github`. Key on the **trusted client IP** (`Fly-Client-IP`; NOT raw
  `X-Forwarded-For`, which `--forwarded-allow-ips=*` makes spoofable) and on the resolved principal.
  Return `429` + `Retry-After`. A coarse global ceiling middleware backs the per-route limits.
- **Tests:** integration — exceed a route's limit → `429` + header; under the limit unaffected; the
  limiter reads the Fly header, not a spoofed XFF. Unit — the key function.
- **Acceptance:** hammer demo; suite green. App-code — deploys. (No migration.)

### V28 · Payload hardening (H3)
- **Build:** a body-size limit (middleware, e.g. reject `Content-Length` over a ceiling with `413`);
  add `max_length` to text fields in `schemas.py` (title/description/name/comment/label/url/…, today
  only `min_length=1`); cap array lengths on `PATCH /cards/batch` and template `cards` (create +
  apply). All additive validation; normal payloads unaffected.
- **Tests:** integration — oversized body → `413`; over-long string / over-large array → `422`;
  representative normal payloads still pass. Unit — schema bounds.
- **Acceptance:** the reject demo; suite green. App-code — deploys.

### V29 · Security headers (H4)
- **Build:** a response middleware setting HSTS (prod HTTPS via `force_https`), `Content-Security-Policy`
  (single-origin: `self` + inline SPA; **report-only first**, then enforce), `X-Content-Type-Options:
  nosniff`, `frame-ancestors 'none'`/`X-Frame-Options`, `Referrer-Policy`. Must not break the SPA or
  `/docs`.
- **Tests:** integration — headers present on API + SPA + `/docs` responses. e2e — SPA still loads and
  operates (no CSP violations in console).
- **Acceptance:** headers-pass demo; suite green. App-code — deploys.

### V30 · DB + cold-start resilience (H5)
- **Build:** set `statement_timeout` (via connect args / `SET`) + tighten pool size and connect
  timeout on **both** the sync board engine and the async auth engine in `db.py`. Goal: a slow query
  on a cold-woken Neon cannot pile up connections and wedge the box.
- **Tests:** integration — a deliberately slow statement is cancelled at the timeout with a clean
  error (not a hang). Confirm both engines honor it.
- **Acceptance:** timeout demo; suite green. App-code — deploys.

## Wave 2 — Sharpen (core)

### V31 · Project fields on epics (P1)
- **Build:** additive migration — `epic.target_date` (`timestamptz` null), `epic.lead` (`varchar`
  null). Schemas expose them; `epic` create/update accept them. Parity: `kan epic create/update
  --target-date/--lead`, MCP `create_epic`/`update_epic` fields.
- **Tests:** integration — set/read/clear each; existing epics read null (back-compat). Unit — schema.
- **Acceptance:** the demo; suite green. Additive migration — deploys, prod-verify.

### V32 · Progress rollup + health (P2)
- **Build:** derived (no writes) — per-epic progress % (`done` children / total non-deleted) + a
  health signal (`on_track` / `at_risk` / `overdue`) from `target_date` vs remaining work. Add to epic
  read + list responses; render on the Epics page (a small progress bar + health pill). Parity in
  `kan epic list`/MCP (the fields ride the epic payload).
- **Tests:** integration — rollup math over seeded child cards; health transitions across the date
  boundary; empty epic → `0%`. Unit — the pure rollup/health function.
- **Acceptance:** `60% · at risk` demo; suite green. No migration — deploys.

### V33 · Cycle model + API (C1)
- **Build:** additive migration — `cycle` table (`id`, `board_id` FK `ON DELETE CASCADE`, `name`,
  `starts_on`, `ends_on`, `created_at`) + nullable `card.cycle_id` FK (`ON DELETE SET NULL`, mirroring
  `epic_id`). CRUD under the board (mirror the saved-views/templates routers): `GET/POST
  /boards/{id}/cycles`, `GET/DELETE …/{cid}`; assign via `PATCH /cards/{id}` (`cycle_id`). Query filter
  `cycle_id`. Parity: `kan cycle list/create/delete` + `kan list --cycle`, MCP `*_cycle` family.
- **Tests:** integration — CRUD; assign/unassign; board-scoping (cross-board cycle id → 404); filter
  returns the cycle's cards. Unit — schema.
- **Acceptance:** create/assign/list demo; suite green. Additive migration — deploys, prod-verify.

### V34 · Cycle burndown / velocity (C2)
- **Build:** cycle-scoped derived metrics reusing the V17 engine (`app.metrics`): burndown (remaining
  story points/count over the `starts_on…ends_on` window from activity), committed-vs-completed,
  velocity. `GET /boards/{id}/cycles/{cid}/metrics` + `kan`/MCP. Active-cycle filter on the board; a
  theme-aware burndown chart on the Dashboard (dataviz conventions, no chart lib).
- **Tests:** integration — burndown over seeded/backdated activity; empty cycle zeroed; window
  scoping; authz. Unit — the burndown/velocity computation (pure).
- **Acceptance:** burndown-line demo; suite green. No migration — deploys.

## Wave 3 — Tail *(Nice-to-have; milestone demos complete without these)*

### V35 · Command palette ⌘K (K1)
- **Build:** a Svelte-5 command menu (⌘/Ctrl-K) over **existing** API actions — no new backend.
  Commands: jump to board/view/epic/dashboard, create card, move card, set a filter, toggle theme.
  Server-authoritative (each command hits the existing API + `refetch()`; no optimistic UI —
  BREADBOARD §7).
- **Tests:** e2e — open palette, run a command, board reflects it.
- **Acceptance:** ⌘K move demo; suite green. Frontend — deploys.

### V36 · Keyboard shortcuts + help overlay (K2)
- **Build:** keyboard nav — focus/move between cards + columns, open/edit a focused card, create in a
  column, `?` help overlay. No hijack while typing in inputs/modals. Frontend-only.
- **Tests:** e2e — drive the board by keyboard.
- **Acceptance:** keyboard-only move demo; suite green. Frontend — deploys.

### V37 · Notification store + inbox API (N1)
- **Build:** additive migration — `notification` (`id`, `user_id` FK, `board_id` FK, `card_id` FK
  null, `kind`, `body`, `read_at` null, `created_at`). Emit-on-event at the write path (a small helper
  like the activity logger, same transaction): `needs_human` raised, a card newly `blocked`, a linked
  PR's CI failed (M4 auto-sync), assignment to you. `GET /api/v1/notifications` (unread/all) + `PATCH`
  (mark read). Owner-scoped. Parity: `kan notify list/read`, MCP `list_notifications`/`mark_read`.
  Poll/pull only (ADR 0007).
- **Tests:** integration — each emitter fires exactly one row; mark-read; owner-scoped (you don't see
  others'). Unit — the emit helper.
- **Acceptance:** `kan notify` demo; suite green. Additive migration — deploys, prod-verify.

### V38 · Signed outbound webhook (N2)
- **Build:** per-board outbound webhook — a target URL + secret in board settings (`autosync`-style
  opt-in). On notification-create, `POST` an HMAC-SHA256-signed JSON payload (mirror the inbound
  `X-Hub-Signature-256` scheme). Rate-limited (V27), best-effort + short backoff (no worker infra in
  MVP), delivery logged. Powers email/Slack/automation downstream.
- **Tests:** integration — signature correctness; opt-in gating (off → no POST); failure logged, not
  fatal. Unit — the signer.
- **Acceptance:** request-bin demo; suite green. Additive migration (board settings) — deploys.

### V39 · Inbox UI + unread badge (N3)
- **Build:** a read-first **Inbox** nav panel listing notifications newest-first with mark-read, + an
  unread-count badge. Poll/refresh (no websockets). Reuses V37's API.
- **Tests:** e2e — renders inbox, marks read, badge updates.
- **Acceptance:** badge demo; suite green. Frontend + reuse — deploys.

---

> **Board mapping.** Tracked on the *Simple Kanban Roadmap* board (dogfooding, as always) as the
> `M6:` epics **EPIC-46…EPIC-50** with cards **KAN-290…KAN-303**; each V-slice above is one card.
> The **simple-markdown** sister app is recorded in
> [docs/simple-markdown-vision.md](../simple-markdown-vision.md) with a human-owned kickoff card
> (**KAN-304**) — it is a *separate* repo/project, not an M6 build slice.
