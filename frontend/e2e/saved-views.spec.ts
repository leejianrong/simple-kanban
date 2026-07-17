import { expect, test, type Page } from "@playwright/test";
import { cleanupE2eBoards, column, openFreshBoard, uniqueTitle } from "./helpers";

// M5 V14 (KAN-247): query depth + saved views. Saving a filtered view and
// switching to it filters the board server-side; the table view renders the same
// (filtered) cards and sorts client-side on a header click. Screenshots use
// testInfo.outputPath so they land under the per-test output dir on any runner.

test.afterAll(async () => {
  await cleanupE2eBoards();
});

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => {
    try {
      localStorage.setItem("kanban.theme", t);
    } catch {
      /* ignore */
    }
  }, theme);
}

// Create a card in a column with an explicit priority via the Add-card form.
async function createCardWithPriority(
  page: Page,
  columnLabel: string,
  title: string,
  priority: string,
): Promise<void> {
  const col = column(page, columnLabel);
  await col.getByRole("button", { name: "Add card" }).click();
  await col.getByPlaceholder("Title (required)").fill(title);
  await col.getByLabel("Priority").selectOption(priority);
  await col.getByRole("button", { name: "Create" }).click();
  await expect(col.locator(".card-dnd", { has: page.getByText(title, { exact: true }) })).toBeVisible();
}

function cardFace(page: Page, columnLabel: string, title: string) {
  return column(page, columnLabel).locator(".card-dnd", {
    has: page.getByText(title, { exact: true }),
  });
}

test("saving a filtered view and switching to it filters the board", async ({ page }) => {
  await openFreshBoard(page);
  const keep = uniqueTitle("keep-high");
  const hide = uniqueTitle("hide-none");
  await createCardWithPriority(page, "Todo", keep, "high");
  await createCardWithPriority(page, "Todo", hide, "none");

  // Both visible with no filter.
  await expect(cardFace(page, "Todo", keep)).toBeVisible();
  await expect(cardFace(page, "Todo", hide)).toBeVisible();

  // Filter by priority=high → only the high card remains (server-side filter).
  await page.getByLabel("Filter by priority").selectOption("high");
  await expect(cardFace(page, "Todo", keep)).toBeVisible();
  await expect(cardFace(page, "Todo", hide)).toHaveCount(0);

  // Save the current query as a named view; it appears in the switcher + is active.
  await page.getByRole("button", { name: "Save view" }).click();
  await page.getByLabel("View name").fill("highs");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const viewSelect = page.getByLabel("Saved view");
  await expect(viewSelect).toHaveValue(/\d+/);
  await expect(viewSelect.locator("option", { hasText: "highs" })).toHaveCount(1);

  // Switch to "All cards" → both visible again.
  await viewSelect.selectOption({ label: "All cards" });
  await expect(cardFace(page, "Todo", keep)).toBeVisible();
  await expect(cardFace(page, "Todo", hide)).toBeVisible();

  // Switch back to the saved view → filtered again.
  await viewSelect.selectOption({ label: "highs" });
  await expect(cardFace(page, "Todo", keep)).toBeVisible();
  await expect(cardFace(page, "Todo", hide)).toHaveCount(0);
});

test("table view renders the cards and sorts on a header click", async ({ page }, testInfo) => {
  await setTheme(page, "light");
  await openFreshBoard(page);
  const alpha = uniqueTitle("aaa");
  const zeta = uniqueTitle("zzz");
  await createCardWithPriority(page, "Todo", zeta, "low");
  await createCardWithPriority(page, "Todo", alpha, "urgent");

  // Flip to the table view.
  await page.getByRole("button", { name: "Table view" }).click();
  const table = page.locator(".card-table");
  await expect(table).toBeVisible();
  const rows = table.locator("tbody tr");
  await expect(rows).toHaveCount(2);

  // Sort by Title ascending → the "aaa" card leads; a second click flips it.
  await page.getByRole("button", { name: "Sort by Title" }).click();
  await expect(rows.first()).toContainText(alpha);
  await page.getByRole("button", { name: "Sort by Title" }).click();
  await expect(rows.first()).toContainText(zeta);

  // Light + dark screenshots (CI-safe path).
  await page.screenshot({ path: testInfo.outputPath("v14-table-light.png"), fullPage: true });
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator(':root[data-theme="dark"]')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("v14-table-dark.png"), fullPage: true });
});
