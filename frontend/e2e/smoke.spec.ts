import { expect, test } from "@playwright/test";
import {
  cardInColumn,
  cleanupE2eBoards,
  createCard,
  dragTo,
  dropzone,
  openFreshBoard,
  uniqueTitle,
} from "./helpers";

// /api/v1 is now owner-gated (M3 V8), so each test opens a REAL session and lands
// on a fresh owned board (openFreshBoard). Deleting the boards afterwards cascades
// away their cards.
test.afterAll(cleanupE2eBoards);

test("load → create → drag-move persists across reload", async ({ page }) => {
  await openFreshBoard(page);

  const title = uniqueTitle("move");
  await createCard(page, "Todo", title);

  await dragTo(page, cardInColumn(page, "Todo", title), dropzone(page, "In Progress"));

  await expect(cardInColumn(page, "In Progress", title)).toBeVisible();
  await expect(cardInColumn(page, "Todo", title)).toHaveCount(0);

  // Server-authoritative: the move survives a full reload.
  await page.reload();
  await expect(cardInColumn(page, "In Progress", title)).toBeVisible();
});

test("failed move reverts the board and surfaces an error", async ({ page }) => {
  await openFreshBoard(page);

  const title = uniqueTitle("moveerr");
  await createCard(page, "Todo", title);

  // Force the move to fail (create/list still hit the real backend).
  await page.route("**/api/v1/cards/*/move", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    }),
  );

  await dragTo(page, cardInColumn(page, "Todo", title), dropzone(page, "Done"));

  // No optimistic UI: the board snaps back to the server order and shows an error
  // (BREADBOARD §7). This guards the fix from PR #7.
  await expect(page.locator(".banner.error")).toBeVisible();
  await expect(cardInColumn(page, "Todo", title)).toBeVisible();
  await expect(cardInColumn(page, "Done", title)).toHaveCount(0);
});
