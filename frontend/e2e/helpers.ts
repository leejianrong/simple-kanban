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

// The transitional SERVICE token (V8, ADR 0013) the backend runs with under e2e
// (set in playwright.config's webServer env). Used only by the cleanup helpers so
// they can read/delete across users on the now-owner-gated API.
const SERVICE_TOKEN = "e2e-service-token";
const SERVICE_HEADERS = { Authorization: `Bearer ${SERVICE_TOKEN}` };

export function uniqueTitle(label = "card"): string {
  return `${E2E_PREFIX}${label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

// A stubbed signed-in user, still used by login.spec (a pure frontend gating test
// that never touches the real API). Its email matches the real e2e login below so
// top-bar assertions are consistent.
export const E2E_USER = {
  id: "00000000-0000-0000-0000-000000000001",
  email: "e2e@example.com",
  is_active: true,
  is_superuser: false,
  is_verified: true,
};

// A REAL backend session (M3 V8): /api/v1 is now owner-gated, so a page.route stub
// of /users/me is no longer enough — the API checks a real httpOnly cookie. The
// e2e-only `POST /auth/test-login` (gated by E2E_AUTH_BYPASS, see playwright.config)
// mints that session. maxRedirects:0 keeps the login's 302→"/" from being followed,
// so the Set-Cookie on the 302 lands in the context's cookie jar directly. Call
// before navigating; the cookie is then sent on the SPA's fetches.
export async function login(page: Page, email = E2E_USER.email): Promise<void> {
  const res = await page.request.post("/auth/test-login", {
    data: { email },
    maxRedirects: 0,
  });
  if (res.status() >= 400) {
    throw new Error(`test-login failed (${res.status()}): ${await res.text()}`);
  }
}

// Create a board via the top-bar switcher (creating switches to it) and wait for
// the board view to settle. Returns the name used.
export async function createBoardViaSwitcher(page: Page, name: string): Promise<string> {
  const switcher = page.locator(".board-switcher");
  await switcher.getByRole("button", { name: "+ New board" }).click();
  await page.getByLabel("Board name").fill(name);
  await switcher.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByLabel("Board", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();
  return name;
}

// Log in (real session), open the SPA, and land on a fresh, empty, owned board —
// the precondition the board specs need now that /api/v1 is owner-gated. A fresh
// board per test also keeps them independent and tolerant of pre-existing data.
export async function openFreshBoard(page: Page): Promise<string> {
  await login(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();
  return createBoardViaSwitcher(page, uniqueTitle("board"));
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

// Delete every board these tests created, via the API. Deleting a board cascades
// away its cards + epics, so this also cleans up anything created on that board.
// Runs as the SERVICE principal (bearer) since /api/v1 is now owner-gated and the
// boards span multiple e2e users.
export async function cleanupE2eBoards(): Promise<void> {
  const ctx: APIRequestContext = await request.newContext({
    baseURL: API_ORIGIN,
    extraHTTPHeaders: SERVICE_HEADERS,
  });
  try {
    const boards = await ctx.get("/api/v1/boards");
    if (boards.ok()) {
      for (const board of await boards.json()) {
        if (typeof board.name === "string" && board.name.startsWith(E2E_PREFIX)) {
          await ctx.delete(`/api/v1/boards/${board.id}`);
        }
      }
    }
  } finally {
    await ctx.dispose();
  }
}

// Delete every card and epic these tests created, via the API (as SERVICE).
export async function cleanupE2eCards(): Promise<void> {
  const ctx: APIRequestContext = await request.newContext({
    baseURL: API_ORIGIN,
    extraHTTPHeaders: SERVICE_HEADERS,
  });
  try {
    const cards = await ctx.get("/api/v1/cards");
    if (cards.ok()) {
      for (const card of await cards.json()) {
        if (typeof card.title === "string" && card.title.startsWith(E2E_PREFIX)) {
          await ctx.delete(`/api/v1/cards/${card.id}`);
        }
      }
    }
    const epics = await ctx.get("/api/v1/epics");
    if (epics.ok()) {
      for (const epic of await epics.json()) {
        if (typeof epic.name === "string" && epic.name.startsWith(E2E_PREFIX)) {
          await ctx.delete(`/api/v1/epics/${epic.id}`);
        }
      }
    }
  } finally {
    await ctx.dispose();
  }
}
