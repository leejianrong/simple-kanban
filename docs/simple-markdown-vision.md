# simple-markdown — vision (sister app to simple-kanban)

> **Status: recorded intent, not started.** This is a *separate* product in its own git repo, not a
> simple-kanban milestone. Kickoff is a human task (board card **KAN-304**). This doc captures the
> vision, the ethos, and — most importantly — the **integration contract** with simple-kanban, since
> that contract shapes both apps and should be settled before either commits to a schema.

## The one-liner

A cloud-hosted, Obsidian-like **markdown notes** app — API-first, agent-drivable — that is the
**docs half** of the simple-kanban ecosystem. Where simple-kanban tracks *work*, simple-markdown
holds the *knowledge*: specs, notes, runbooks, meeting notes — cross-linked to the board.

## Why it exists (strategic fit)

- **It's the proven pairing.** Jira has Confluence; Linear has Documents. A docs sibling to a tracker
  is a well-trodden, high-value combination.
- **It answers a gap we deliberately declined.** simple-kanban chose *not* to add file attachments /
  rich documents (needs storage infra, off the "simple" line — see the M5 competitive delta and the
  M6 shaping). A *sibling* app answers "where does the rich content live?" without growing kanban into
  Notion. Each app stays simple; the **integration** is the combined value.
- **It's agent-native, like its sibling.** An agent that drives the board with a PAT should, with the
  same identity, read and write the notes — maintaining a card's spec doc *as it works the card*.

## Ethos carried over from simple-kanban

The point of a sibling (not a fork) is a shared philosophy. simple-markdown inherits:

- **Cloud-only, last-write-wins, no real-time** (simple-kanban ADR 0007). This is a *deliberate*
  simplification vs. Obsidian's local-first files and Notion's realtime CRDT collaboration — and it
  keeps the two apps consistent. A note is server-authoritative; concurrent edits are LWW, same as a
  card.
- **API-first** (ADR 0005): every UI action is a plain REST call; the SPA is a thin client.
- **MCP + CLI parity**: a `smd` CLI + an MCP server, mirroring `kan` + the kanban MCP, so agents drive
  notes exactly as they drive the board.
- **Single deployable artifact, one origin** (ADR 0003): FastAPI serves the built SPA; same
  single-origin CSP story.
- **Same stack**: FastAPI + SQLAlchemy (sync) + Postgres + Alembic; Svelte 5 runes SPA; `uv` + `npm`;
  Fly.io + Neon; the same CI shape (lint + unit + integration + build + e2e).

## The integration contract (settle this FIRST)

This is the part that constrains both apps, so design it before schemas.

1. **Shared identity.** One account, one set of PATs, spanning both apps. Options, cheapest-first:
   - **Shared `AUTH_SECRET` + session/PAT format** — simple-markdown validates the *same* cookie
     session and `kanban_pat_…` tokens simple-kanban issues (a PAT resolves to the same `User`).
     Simplest; couples the two on a shared secret + a shared or replicated `user` table.
   - **A tiny shared auth service / identity table** both apps read. Cleaner long-term; more infra.
   - Decision deferred to the shaping; **shared-secret PAT validation is the MVP lean.**
2. **Cross-linking, both directions.**
   - **Note → card:** `[[KAN-123]]` wikilinks in note text resolve to a board card (title, column,
     link out). The Obsidian `[[wikilink]]` idiom, spanning apps.
   - **Card → note:** a card's existing **work-links** (M4) already model "this card links to a URL";
     a note is just a first-class link target. Optionally a typed `spec` link.
   - **Embeds:** a note can embed a *live* board view (a saved-view query rendered read-only), so a
     project spec shows its own task list.
3. **Discovery.** Each app links to the other in its nav when the sibling origin is configured
   (an env var — no hard dependency; either runs standalone).

## Shape sketch (for the eventual build-plan-product pass)

- **Data:** `note` (id, owner_id, title, `body` markdown text, folder/path, updated_at) + a
  `note_link` edge table for resolved `[[…]]` references (to notes and to `KAN-`/`EPIC-` tickets),
  enabling a backlinks panel and an eventual graph view. Text lives in Postgres — **markdown is just
  text**, no storage infra needed for the core.
- **Editor:** **CodeMirror 6** (what Obsidian uses) — live-preview markdown, wikilink autocomplete.
  **Do not hand-roll an editor.**
- **Surfaces:** a file/folder tree, the editor, a backlinks panel, full-text search (Postgres FTS,
  exactly like simple-kanban V15), and a read-only "embed a board view" block.

## Deliberate non-goals (hold the line, like the sibling does)

- **No local-first sync / CRDTs.** Cloud-only LWW. Local-first is a different, much harder product.
- **No real-time multiplayer.** Poll/refresh, LWW (ADR 0007 parity).
- **Attachments are deferred.** Core is text-only markdown in Postgres. When images/files are truly
  needed, reach for object storage (Cloudflare R2) — *not* before, and *not* in the MVP.
- **No plugin ecosystem.** Obsidian's plugins are its moat and its complexity; simple-markdown stays a
  focused core.

## First steps (when kicked off — KAN-304)

1. Decide the **identity contract** (shared-secret PAT validation vs. shared auth service).
2. New repo `simple-markdown`; run **build-plan-product** → shaping, mirroring how simple-kanban was
   planned (REQS → FRAME → PRD/CONTEXT → SHAPING → BREADBOARD → slices).
3. Thin vertical slice first: create/read/edit a note via API + a minimal SPA editor; then FTS; then
   `[[KAN-x]]` resolution against simple-kanban; then the CLI + MCP.
