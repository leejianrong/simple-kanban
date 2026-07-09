import { expect, test } from "@playwright/test";
import { createBoardViaSwitcher, login, uniqueTitle } from "./helpers";

// M3 V8 acceptance (ADR 0013): the isolation demo. A second logged-in user cannot
// see or touch the first user's board — enforced server-side, so it holds in both
// the UI (board switcher) and the raw API. Two separate browser contexts give two
// independent cookie sessions (two distinct users). This spec uses per-run unique
// emails, so it cleans up A's board in-test (as A) rather than via the shared
// afterAll helper, which only knows the default e2e user (V10, ADR 0015).

test("a second user cannot see or touch the first user's board", async ({ browser }) => {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const emailA = `e2e-alice-${stamp}@example.com`;
  const emailB = `e2e-bob-${stamp}@example.com`;

  // User A: log in, create a board.
  const ctxA = await browser.newContext();
  const pageA = await ctxA.newPage();
  await login(pageA, emailA);
  await pageA.goto("/");
  await expect(pageA.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();
  const boardA = await createBoardViaSwitcher(pageA, uniqueTitle("aliceboard"));

  // Look up A's board id via the API (as A).
  const aBoards = (await pageA.request.get("/api/v1/boards").then((r) => r.json())) as {
    id: number;
    name: string;
  }[];
  const aBoard = aBoards.find((b) => b.name === boardA);
  expect(aBoard, "A's board should exist for A").toBeTruthy();
  const aBoardId = aBoard!.id;

  // User B: log in in a separate context (separate cookie jar → a different user).
  const ctxB = await browser.newContext();
  const pageB = await ctxB.newPage();
  await login(pageB, emailB);
  await pageB.goto("/");
  await expect(pageB.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();

  // UI: B's board switcher does not list A's board.
  await expect(pageB.locator(".board-switcher")).not.toContainText(boardA);

  // API: B is forbidden from reading A's board or its cards, and B's own board
  // list omits A's board entirely (owner-scoped).
  expect((await pageB.request.get(`/api/v1/boards/${aBoardId}`)).status()).toBe(403);
  expect((await pageB.request.get(`/api/v1/cards?board_id=${aBoardId}`)).status()).toBe(403);
  const bBoards = (await pageB.request.get("/api/v1/boards").then((r) => r.json())) as {
    name: string;
  }[];
  expect(bBoards.map((b) => b.name)).not.toContain(boardA);

  // Clean up A's board as A (owner-gated; cascades its cards/epics away).
  await pageA.request.delete(`/api/v1/boards/${aBoardId}`);

  await ctxA.close();
  await ctxB.close();
});
