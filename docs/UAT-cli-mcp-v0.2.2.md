# UAT: CLI + MCP distribution artifacts (v0.2.2)

**Ticket:** KAN-85
**Artifacts under test:** the `ghcr.io/leejianrong/simple-kanban-mcp` MCP image and the `kan` CLI binary, both from the v0.2.2 release
**Date:** 2026-07-13
**Tester:** project maintainer (PM-run UAT)
**Result:** all test cases passed. No open defects.

## Purpose

This is an acceptance record for the two things a v0.2.2 end user actually installs: the published MCP Docker image and the standalone `kan` CLI binary. It exists so a maintainer, or a team picking the project up later, can trust that those artifacts pull, install, and run against the live API without rebuilding from source. Everything below was executed by hand; the results are transcribed as observed, not inferred.

## Environment

| Item | Value |
|------|-------|
| OS | WSL2, Ubuntu 22.04 baseline |
| glibc | 2.35 |
| Container runtime | Docker (available) |
| Live API | `https://simple-kanban-jian.fly.dev` (Fly.io + Neon, free tier, scales to zero) |
| Auth | per-user PAT (`kanban_pat_…`) supplied as `KANBAN_TOKEN` |
| Test date | 2026-07-13 |

Because the Neon free tier scales to zero, the first request after an idle period is slow (~1s cold start). That is expected and not treated as a failure below.

## Scope

In scope:

- Pulling the MCP image from GHCR, including whether an unauthenticated pull works (public package visibility).
- The MCP protocol handshake and tool inventory.
- One authenticated end-to-end MCP call against the live API.
- Installing the `kan` Linux binary and running it from an arbitrary directory.
- CLI read commands and a full create/update/move/delete cycle against the live API.
- The glibc regression from v0.2.0 (tracked under KAN-81) — confirming it is fixed in the v0.2.2 binary.

Out of scope for this round:

- The Intel-mac `kan-macos-x86_64` asset, which was still building on a free-tier runner at test time. It was not exercised here.
- Windows and Apple-silicon targets.
- Load, concurrency, or security testing — this is a functional acceptance pass on the distribution artifacts only.

## Results summary

Nine cases, all passed.

| # | Case | Result |
|---|------|--------|
| MCP-1 | Unauthenticated image pull (public visibility) | Pass |
| MCP-2 | MCP protocol handshake + tool list | Pass |
| MCP-3 | Authenticated end-to-end call (`list_boards`) | Pass |
| CLI-1 | Binary runs on glibc 2.35 (v0.2.0 regression fixed) | Pass |
| CLI-2 | Install to `~/.local/bin` and run from any directory | Pass |
| CLI-3 | `warmup` (no token required) | Pass |
| CLI-4 | Read commands (`board list`, `epic list`, `list`) | Pass |
| CLI-5 | Full CRUD cycle on a throwaway card | Pass |
| CLI-6 | `--json` output and exit codes | Pass |

## Test cases

### MCP-1 — Unauthenticated image pull

**Steps:** `docker logout ghcr.io`, then `docker pull ghcr.io/leejianrong/simple-kanban-mcp:latest`.

**Expected:** the pull succeeds without credentials, confirming the GHCR package is public.

**Actual:** the pull succeeded unauthenticated, resolving digest `sha256:076ecab24e2ebdc3b8d14ea8cb465c0e7cfcb28e926688e50c5f6dae469428f6`. The `publish-mcp-image.yml` workflow had succeeded for v0.2.2 (and for v0.2.1 and v0.2.0 before it). Tags `latest`, `0.2.2`, `0.2`, and `0` are published.

**Pass/fail:** Pass.

### MCP-2 — Protocol handshake and tool inventory

**Steps:** run the image over stdio with a dummy token and pipe JSON-RPC at it:
`docker run --rm -i -e KANBAN_API_URL=… -e KANBAN_TOKEN=dummy <image>`, sending `initialize` then `tools/list`.

**Expected:** `initialize` returns server info and a protocol version; `tools/list` returns the full tool set. No auth needed for the handshake itself.

**Actual:** `initialize` returned `serverInfo` name `kanban`, version `1.28.1`, protocol version `2024-11-05`. `tools/list` returned 26 tools, including `add_comment`, `add_dependency`, `add_link`, `claim_card`, `create_board`, `create_card`, `create_cards`, `create_epic`, `list_boards`, `list_cards`, `move_card`, and `warmup`.

**Pass/fail:** Pass.

### MCP-3 — Authenticated end-to-end call

**Steps:** run the image with a real PAT as `KANBAN_TOKEN` and issue `tools/call list_boards`.

**Expected:** the call returns the caller's boards from the live API, proving the unauthenticated image pull and a PAT-authenticated API call compose correctly.

**Actual:** `list_boards` returned board id 5, "Simple Kanban Roadmap", and board id 6, "Engine Room" — the caller's own boards.

**Pass/fail:** Pass.

**Config note:** the MCP server takes three environment variables — `KANBAN_API_URL`, `KANBAN_TOKEN` (the PAT), and `KANBAN_BOARD_ID` (the default board). Omitting `KANBAN_BOARD_ID` makes list/create span all boards and land creates on the earliest board, so set it in `.mcp.json` to avoid targeting the wrong board.

### CLI-1 — Binary runs on glibc 2.35 (regression check)

**Context:** the v0.2.0 Linux binary failed to run on this glibc-2.35 box with `libpython3.12.so.1.0: GLIBC_2.38 not found`, because it had been built on ubuntu-24.04. That defect was found and fixed under KAN-81, which moved the build into a manylinux_2_28 container (glibc 2.28 floor).

**Steps:** run the v0.2.2 `kan-linux-x86_64` binary on the glibc-2.35 environment.

**Expected:** it runs — no missing-symbol error.

**Actual:** it ran. The v0.2.2 binary supports glibc >= 2.28, which covers Ubuntu 20.04+, Debian 11+, and RHEL/Rocky/Alma 8+.

**Pass/fail:** Pass. (The underlying defect was resolved under KAN-81 before this round; this case verifies the fix shipped.)

### CLI-2 — Install and run from any directory

**Steps:** `gh release download v0.2.2 --pattern kan-linux-x86_64` (also available from the Releases page), then `install -m 0755 kan-linux-x86_64 ~/.local/bin/kan`.

**Expected:** with `~/.local/bin` on PATH, `kan` resolves and runs regardless of the current directory.

**Actual:** `which kan` returned `/home/jian/.local/bin/kan`, and `kan` ran from `/tmp`. `~/.local/bin` is the user-level install target; a system-wide `/usr/local/bin` install would need sudo.

**Pass/fail:** Pass.

### CLI-3 — `warmup`

**Steps:** `kan warmup` (env: `KANBAN_API_URL`, `KANBAN_TOKEN`, `KANBAN_BOARD_ID=5`).

**Expected:** the API wakes; exit 0; no token required.

**Actual:** returned "ok / API is awake" with exit 0. The command needs no token.

**Pass/fail:** Pass.

### CLI-4 — Read commands

**Steps:** `kan --help`, `kan board list`, `kan epic list`, `kan list --limit 5`.

**Expected:** help renders; the board, epic, and card reads return live data; the card list respects `--limit` and surfaces pagination.

**Actual:** `kan --help` printed usage. `kan board list` returned the two boards. `kan epic list` returned epics (EPIC-3 through EPIC-8 shown). `kan list --limit 5` returned 5 cards plus a keyset-pagination "next cursor".

**Pass/fail:** Pass.

### CLI-5 — Full CRUD cycle

**Steps:** create, read, update, move twice, delete, and confirm the delete, using a throwaway card:

- `kan create "uat-cli-smoke (delete me)" --json`
- `kan get 82`
- `kan update 82 --points 3`
- `kan move 82 in_progress` then `kan move 82 done`
- `kan delete 82 --yes`
- `kan get 82`

**Expected:** each step succeeds; the final `get` reports the card gone.

**Actual:** create returned KAN-82 (id 82) in `todo`. `get 82` succeeded. `update 82 --points 3` set `story_points` to 3. The two moves landed the card in `done`. `delete 82 --yes` returned "deleted card 82". The final `get 82` returned `kan: 404: Card not found`, confirming the delete. Test data was cleaned up.

**Pass/fail:** Pass.

### CLI-6 — Scripting affordances

**Steps:** observed across the cases above — `--json` output (e.g. on `kan create`) and process exit codes.

**Expected:** `--json` emits parseable output for piping; commands return distinct exit codes usable in scripts.

**Actual:** `--json` produced structured output suitable for piping, and commands returned distinct exit codes (exit 0 on `warmup`; a non-zero, 404-bearing error on the missing card).

**Pass/fail:** Pass.

## Defects and follow-ups

No defects were opened in this round.

One prior defect is relevant as resolved: the v0.2.0 Linux binary's `GLIBC_2.38 not found` failure was fixed under KAN-81 by building in a manylinux_2_28 container. CLI-1 confirms the fix reached the v0.2.2 artifact.

Follow-ups, not defects:

- The Intel-mac `kan-macos-x86_64` asset was still building on a free-tier runner at test time and was not exercised. It should be covered in a later round once the release assets are complete.
- Windows and Apple-silicon targets remain untested here.

## Conclusion

The v0.2.2 MCP image and `kan` CLI binary both work end to end for an end user: the image pulls unauthenticated from a public GHCR package, handshakes over the MCP protocol, and serves live data with a PAT; the CLI installs from the GitHub Release, runs on glibc 2.28+, and drives the full card lifecycle against the live API. The glibc regression that broke v0.2.0 on this environment is fixed. v0.2.2 is accepted for the Linux and MCP artifacts tested; the macOS Intel asset is deferred to a follow-up round.
