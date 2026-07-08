import { expect, test } from "@playwright/test";
import { E2E_USER } from "./helpers";

// M3 V6 (A9): the logged-out landing, a stubbed GitHub login that lands on the
// board and survives reload, and logout returning to the landing. The GitHub
// round-trip is stubbed via page.route (no real OAuth), consistent with the
// existing e2e style: a mutable `loggedIn` flag flips when "GitHub" is hit.
test("logged out → sign in → board (survives reload) → log out → landing", async ({ page }) => {
  let loggedIn = false;

  // Who-am-I reflects the session flag.
  await page.route("**/users/me", (route) =>
    loggedIn
      ? route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(E2E_USER),
        })
      : route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        }),
  );
  // "GitHub" approves and bounces straight back to the SPA root; the authorize
  // endpoint normally returns the real GitHub URL (see api.ts).
  await page.route("**/auth/github/authorize", (route) => {
    loggedIn = true;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authorization_url: "/" }),
    });
  });
  await page.route("**/auth/logout", (route) => {
    loggedIn = false;
    route.fulfill({ status: 204, body: "" });
  });

  // Logged out → the landing, no board.
  await page.goto("/");
  const signIn = page.getByRole("button", { name: /Sign in with GitHub/ });
  await expect(signIn).toBeVisible();
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toHaveCount(0);

  // Sign in → back to the app → the board.
  await signIn.click();
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();
  await expect(page.getByText(E2E_USER.email)).toBeVisible();

  // The session survives a full reload.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toBeVisible();

  // Log out → back to the landing.
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("button", { name: /Sign in with GitHub/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Todo", exact: true })).toHaveCount(0);
});
