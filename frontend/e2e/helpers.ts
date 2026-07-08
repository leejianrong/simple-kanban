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

// The epic list item (in the Epics view) matched by its name.
export function epicItem(page: Page, name: string): Locator {
  return page.locator(".epic-card", { has: page.getByText(name, { exact: true }) });
}

// Create an epic via the Epics view; returns its assigned ticket (e.g. "EPIC-1")
// so callers can assert a linked story's epic tag. Leaves the Epics view open.
export async function createEpic(page: Page, name: string): Promise<string> {
  await page.getByRole("button", { name: "Epics", exact: true }).click();
  await page.getByRole("button", { name: "+ New epic" }).click();
  await page.getByPlaceholder("Epic name (required)").fill(name);
  await page.getByRole("button", { name: "Create" }).click();
  const item = epicItem(page, name);
  await expect(item).toBeVisible();
  return (await item.locator(".ticket").innerText()).trim();
}

// Create a story on the board linked to an existing epic (by its ticket + name).
export async function createStoryUnder(
  page: Page,
  columnLabel: string,
  title: string,
  epicTicket: string,
  epicName: string,
): Promise<void> {
  await page.getByRole("button", { name: "Board", exact: true }).click();
  const col = column(page, columnLabel);
  await col.getByRole("button", { name: "+ Add card" }).click();
  await col.getByPlaceholder("Title (required)").fill(title);
  await col.getByLabel("Epic", { exact: true }).selectOption({ label: `${epicTicket} · ${epicName}` });
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

// Delete every card and epic these tests created, via the API.
export async function cleanupE2eCards(): Promise<void> {
  const ctx: APIRequestContext = await request.newContext({ baseURL: API_ORIGIN });
  try {
    const cards = await ctx.get("/api/cards");
    if (cards.ok()) {
      for (const card of await cards.json()) {
        if (typeof card.title === "string" && card.title.startsWith(E2E_PREFIX)) {
          await ctx.delete(`/api/cards/${card.id}`);
        }
      }
    }
    const epics = await ctx.get("/api/epics");
    if (epics.ok()) {
      for (const epic of await epics.json()) {
        if (typeof epic.name === "string" && epic.name.startsWith(E2E_PREFIX)) {
          await ctx.delete(`/api/epics/${epic.id}`);
        }
      }
    }
  } finally {
    await ctx.dispose();
  }
}
