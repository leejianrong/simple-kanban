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

// /api/v1 is owner-gated (M3 V8): each test opens a real session on a fresh board.
test.afterAll(cleanupE2eBoards);

// Finding 2: a card in edit mode still sits inside the drag zone, so a pointer
// drag that starts on a form field must NOT pick up and move the card — the user
// is editing, not dragging.
test("dragging from within a card's edit form must not move the card", async ({ page }) => {
  await openFreshBoard(page);

  const title = uniqueTitle("editdrag");
  await createCard(page, "Todo", title);

  // Open the edit form for this card.
  await cardInColumn(page, "Todo", title).getByRole("button", { name: "Edit" }).click();
  const form = page.locator(".card-form");
  await expect(form).toBeVisible();
  const titleInput = form.getByPlaceholder("Title (required)");
  await expect(titleInput).toHaveValue(title);

  // Attempt a drag that starts on the title input and travels to the Done column.
  await dragTo(page, titleInput, dropzone(page, "Done"));

  // The edit form must still be open and the card must not have moved to Done.
  await expect(form).toBeVisible();
  await expect(cardInColumn(page, "Done", title)).toHaveCount(0);
});

// Probe: the edit form also has non-interactive chrome (the read-only ticket
// label). Dragging from there must not move the card either.
test("dragging from a card's edit-form chrome must not move the card", async ({ page }) => {
  await openFreshBoard(page);

  const title = uniqueTitle("editchrome");
  await createCard(page, "Todo", title);

  await cardInColumn(page, "Todo", title).getByRole("button", { name: "Edit" }).click();
  const form = page.locator(".card-form");
  await expect(form).toBeVisible();

  // Start the drag on the read-only ticket label (non-interactive).
  await dragTo(page, form.locator(".ticket"), dropzone(page, "Done"));

  await expect(form).toBeVisible();
  await expect(cardInColumn(page, "Done", title)).toHaveCount(0);
});
