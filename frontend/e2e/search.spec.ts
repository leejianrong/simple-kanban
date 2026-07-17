import { expect, test } from "@playwright/test";
import { cardInColumn, cleanupE2eBoards, createCard, openFreshBoard, uniqueTitle } from "./helpers";

// M5 V15 (KAN-248) full-text search: typing in the top-bar search box calls the
// query API (GET /cards?q=) and the board re-renders to the server's ranked hits.
// Screenshots go to per-test output artifacts (testInfo.outputPath — CI-safe).

test.afterAll(async () => {
  await cleanupE2eBoards();
});

test("top-bar search filters the board to matching cards", async ({ page }) => {
  await openFreshBoard(page);

  // A card that matches and one that doesn't (unique tokens so the search is exact
  // even against pre-existing dev data on the shared DB).
  const token = `zpqx${Date.now()}`;
  const match = uniqueTitle(`search-${token}`);
  const other = uniqueTitle("search-other");
  await createCard(page, "Todo", match);
  await createCard(page, "Todo", other);

  // Both visible before searching.
  await expect(cardInColumn(page, "Todo", match)).toBeVisible();
  await expect(cardInColumn(page, "Todo", other)).toBeVisible();

  // Type the matching token — debounced setQuery -> refetch shows only the hit.
  await page.getByRole("searchbox", { name: "Search cards" }).fill(token);
  await expect(cardInColumn(page, "Todo", match)).toBeVisible();
  await expect(cardInColumn(page, "Todo", other)).toHaveCount(0);

  // Clearing the box restores the full board (server-authoritative no-op).
  await page.getByRole("searchbox", { name: "Search cards" }).fill("");
  await expect(cardInColumn(page, "Todo", other)).toBeVisible();
});

test("search box screenshot", async ({ page }, testInfo) => {
  await openFreshBoard(page);
  const token = `shot${Date.now()}`;
  const title = uniqueTitle(`search-${token}`);
  await createCard(page, "Todo", title);
  await page.getByRole("searchbox", { name: "Search cards" }).fill(token);
  await expect(cardInColumn(page, "Todo", title)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("search-results.png"), fullPage: true });
});
