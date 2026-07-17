import { expect, test } from "@playwright/test";
import { cleanupE2eBoards, createCard, openFreshBoard, uniqueTitle } from "./helpers";

// KAN-18 activity feed: the panel renders recent, newest-first activity for the
// active board, and honours the read API. Also captures light + dark screenshots
// for PM review (saved to the worktree root).

const WORKTREE = "/home/jian/tutorials/agentic-course/simple-kanban/.claude/worktrees/agent-a29e7871cfc9dfec8";

test.afterAll(async () => {
  await cleanupE2eBoards();
});

async function setTheme(page: import("@playwright/test").Page, theme: "light" | "dark") {
  await page.addInitScript((t) => {
    try {
      localStorage.setItem("kanban.theme", t);
    } catch {
      /* ignore */
    }
  }, theme);
}

test("activity panel renders recorded activity, newest first", async ({ page }) => {
  await openFreshBoard(page);

  // Generate a few activity rows: two creates + one move.
  const a = uniqueTitle("activity-a");
  const b = uniqueTitle("activity-b");
  await createCard(page, "Todo", a);
  await createCard(page, "Todo", b);

  // Open the Activity view via the top-bar nav.
  await page.getByRole("button", { name: "Activity", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Activity", exact: true })).toBeVisible();
  const feed = page.locator(".feed");
  await expect(feed).toBeVisible();

  // At least the two card-created rows (plus the board-created row) show up, and
  // the newest (the second card created) leads the list.
  const rows = feed.locator(".feed-row");
  await expect(rows.first()).toContainText(b);
  expect(await rows.count()).toBeGreaterThanOrEqual(3);
});

test("activity panel screenshots — light + dark", async ({ page }) => {
  await setTheme(page, "light");
  await openFreshBoard(page);
  await createCard(page, "Todo", uniqueTitle("shot"));
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.locator(".feed")).toBeVisible();
  await page.screenshot({ path: `${WORKTREE}/kan18-activity-light.png`, fullPage: true });

  // Flip to dark via the top-bar theme toggle and re-shoot the same panel.
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator(':root[data-theme="dark"]')).toBeVisible();
  await page.screenshot({ path: `${WORKTREE}/kan18-activity-dark.png`, fullPage: true });
});
