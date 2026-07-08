import { expect, test } from "@playwright/test";
import {
  cardInColumn,
  cleanupE2eCards,
  createEpic,
  createStoryUnder,
  epicItem,
  uniqueTitle,
} from "./helpers";

test.afterAll(cleanupE2eCards);

// Milestone 2 V1 demo (ADR 0009): epics live in their own view with an EPIC-
// ticket; the board shows stories, each tagged with its epic's name. Create an
// epic, link a story to it, and assert the tag + rollup render and survive reload.
test("create an epic (own view), link a story, tag + rollup persist", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();

  const epicName = uniqueTitle("epic");
  const storyTitle = uniqueTitle("story");

  // Epic is created in the Epics view and gets an EPIC- ticket (not KAN-).
  const epicTicket = await createEpic(page, epicName);
  expect(epicTicket).toMatch(/^EPIC-\d+$/);

  // Link a story to the epic from the board.
  await createStoryUnder(page, "Todo", storyTitle, epicTicket, epicName);

  // The story card shows the epic's name as a tag.
  const storyCard = cardInColumn(page, "Todo", storyTitle);
  await expect(storyCard.locator(".epic-tag")).toHaveText(epicName);

  // The Epics view rolls the story up under its epic.
  await page.getByRole("button", { name: "Epics", exact: true }).click();
  await expect(epicItem(page, epicName).locator(".epic-stories")).toContainText(storyTitle);

  // Server-authoritative: the link survives a full reload.
  await page.reload();
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(cardInColumn(page, "Todo", storyTitle).locator(".epic-tag")).toHaveText(epicName);
});
