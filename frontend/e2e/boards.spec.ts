import { expect, test } from "@playwright/test";
import {
  cardInColumn,
  cleanupE2eBoards,
  createCard,
  loginStub,
  uniqueTitle,
} from "./helpers";

// M3 V7 demo: create a second board, add a card there, and confirm the first
// board is unaffected — across a reload. The board switcher + boards/cards APIs
// hit the real backend (only /users/me is stubbed), so we clean up the board
// afterwards (its cards cascade away with it).
test.beforeEach(({ page }) => loginStub(page));
test.afterAll(cleanupE2eBoards);

test("second board isolates its cards from the first, across reload", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();

  const switcher = page.locator(".board-switcher");
  const boardSelect = page.getByLabel("Board", { exact: true });

  // Create a second board via the switcher — creating switches to it.
  const boardName = uniqueTitle("board");
  await switcher.getByRole("button", { name: "+ New board" }).click();
  await page.getByLabel("Board name").fill(boardName);
  await switcher.getByRole("button", { name: "Create", exact: true }).click();
  await expect(boardSelect).toBeVisible();

  // Add a card on the new board.
  const cardTitle = uniqueTitle("bcard");
  await createCard(page, "Todo", cardTitle);
  await expect(cardInColumn(page, "Todo", cardTitle)).toBeVisible();

  // Switch back to the Default Board — the new board's card must not appear.
  await boardSelect.selectOption({ label: "Default Board" });
  await expect(cardInColumn(page, "Todo", cardTitle)).toHaveCount(0);

  // Reload: server-authoritative + persisted selection keeps us on Default Board,
  // still without the other board's card.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();
  await expect(cardInColumn(page, "Todo", cardTitle)).toHaveCount(0);

  // Switch to the new board — its card is there and survived the reload.
  await boardSelect.selectOption({ label: boardName });
  await expect(cardInColumn(page, "Todo", cardTitle)).toBeVisible();
});
