import {
  expect,
  request,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";

// Every card these tests create is prefixed so they can be cleaned up and so the
// suite tolerates pre-existing dev data (tests run against the docker-compose DB).
export const E2E_PREFIX = "e2e-";
const API_ORIGIN = "http://localhost:8000";

export function uniqueTitle(label = "card"): string {
  return `${E2E_PREFIX}${label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

export function column(page: Page, label: string): Locator {
  return page.locator(".column", {
    has: page.getByRole("heading", { name: label, exact: true }),
  });
}

export function dropzone(page: Page, label: string): Locator {
  return column(page, label).locator(".cards");
}

// A card's face (view mode) within a given column, matched by its title text.
// Note: only matches in view mode — in edit mode the title lives in an input.
export function cardInColumn(page: Page, label: string, title: string): Locator {
  return dropzone(page, label).locator(".card-dnd", {
    has: page.getByText(title, { exact: true }),
  });
}

export async function createCard(
  page: Page,
  columnLabel: string,
  title: string,
): Promise<void> {
  const col = column(page, columnLabel);
  await col.getByRole("button", { name: "+ Add card" }).click();
  await col.getByPlaceholder("Title (required)").fill(title);
  await col.getByRole("button", { name: "Create" }).click();
  await expect(cardInColumn(page, columnLabel, title)).toBeVisible();
}

// Create an epic; returns its assigned ticket number (e.g. "KAN-3"), read off
// the card face so callers can assert a child story's parent ref.
export async function createEpic(
  page: Page,
  columnLabel: string,
  title: string,
): Promise<string> {
  const col = column(page, columnLabel);
  await col.getByRole("button", { name: "+ Add card" }).click();
  await col.getByPlaceholder("Title (required)").fill(title);
  await col.getByLabel("Kind").selectOption("epic");
  await col.getByRole("button", { name: "Create" }).click();
  const face = cardInColumn(page, columnLabel, title);
  await expect(face).toBeVisible();
  return (await face.locator(".ticket").innerText()).trim();
}

// Create a story parented under an existing epic (identified by its ticket + title).
export async function createStoryUnder(
  page: Page,
  columnLabel: string,
  title: string,
  parentTicket: string,
  parentTitle: string,
): Promise<void> {
  const col = column(page, columnLabel);
  await col.getByRole("button", { name: "+ Add card" }).click();
  await col.getByPlaceholder("Title (required)").fill(title);
  // Kind defaults to Story; pick the parent epic by its option label.
  await col.getByLabel("Parent epic").selectOption({ label: `${parentTicket} · ${parentTitle}` });
  await col.getByRole("button", { name: "Create" }).click();
  await expect(cardInColumn(page, columnLabel, title)).toBeVisible();
}

// svelte-dnd-action drives on pointer/mouse move with a movement threshold, so
// a coarse dragTo() won't trigger it — we drive low-level mouse steps instead.
export async function dragTo(
  page: Page,
  source: Locator,
  targetZone: Locator,
): Promise<void> {
  const s = await source.boundingBox();
  const t = await targetZone.boundingBox();
  if (!s || !t) throw new Error("missing bounding box for drag");

  const sx = s.x + s.width / 2;
  const sy = s.y + s.height / 2;
  const tx = t.x + t.width / 2;
  const ty = t.y + Math.min(t.height / 2, 40);

  await page.mouse.move(sx, sy);
  await page.mouse.down();
  await page.mouse.move(sx, sy - 8, { steps: 4 }); // nudge past the threshold
  await page.mouse.move(tx, ty, { steps: 20 }); // travel to the target zone
  await page.waitForTimeout(200);
  await page.mouse.move(tx, ty, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(300); // let flip animation + refetch settle
}

// Delete every card these tests created, via the API.
export async function cleanupE2eCards(): Promise<void> {
  const ctx: APIRequestContext = await request.newContext({ baseURL: API_ORIGIN });
  try {
    const res = await ctx.get("/api/cards");
    if (res.ok()) {
      for (const card of await res.json()) {
        if (typeof card.title === "string" && card.title.startsWith(E2E_PREFIX)) {
          await ctx.delete(`/api/cards/${card.id}`);
        }
      }
    }
  } finally {
    await ctx.dispose();
  }
}
