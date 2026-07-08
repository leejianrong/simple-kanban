import { expect, test } from "@playwright/test";
import {
  cardInColumn,
  cleanupE2eCards,
  createEpic,
  createStoryUnder,
  uniqueTitle,
} from "./helpers";

test.afterAll(cleanupE2eCards);

// Milestone 2 V1 demo: create an epic, then a story under it, and assert the
// kind badges + the story's `↳ KAN-n` parent ref render and survive a reload.
test("create an epic and a story under it → badges + parent ref persist", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();

  const epicTitle = uniqueTitle("epic");
  const storyTitle = uniqueTitle("story");

  const epicTicket = await createEpic(page, "Todo", epicTitle);

  const epicCard = cardInColumn(page, "Todo", epicTitle);
  await expect(epicCard.locator(".kind")).toHaveText("Epic");

  await createStoryUnder(page, "Todo", storyTitle, epicTicket, epicTitle);

  const storyCard = cardInColumn(page, "Todo", storyTitle);
  await expect(storyCard.locator(".kind")).toHaveText("Story");
  await expect(storyCard.locator(".parent-ref")).toHaveText(`↳ ${epicTicket}`);

  // Server-authoritative: the kind + parent survive a full reload.
  await page.reload();
  await expect(cardInColumn(page, "Todo", epicTitle).locator(".kind")).toHaveText("Epic");
  const storyAfter = cardInColumn(page, "Todo", storyTitle);
  await expect(storyAfter.locator(".kind")).toHaveText("Story");
  await expect(storyAfter.locator(".parent-ref")).toHaveText(`↳ ${epicTicket}`);
});
