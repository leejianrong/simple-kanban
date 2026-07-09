import { defineConfig, devices } from "@playwright/test";

// End-to-end smoke tests. Playwright brings up the full local stack itself:
// the FastAPI backend (:8000) and the Vite dev server (:5173, which proxies
// /api → :8000). A local Postgres must already be running —
// `docker compose up -d db` from the repo root (same prereq as running the
// backend normally). Tests are self-contained: each creates cards with a unique
// title prefix and cleans them up, so they tolerate pre-existing dev data.
const CI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // shared backend/DB — keep specs sequential for determinism
  workers: 1,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  reporter: CI ? "line" : "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      // Migrate then serve the API. Uses the default DATABASE_URL (the
      // docker-compose Postgres). cwd is this config's dir (frontend/).
      command:
        'sh -c "cd ../backend && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000"',
      port: 8000,
      reuseExistingServer: !CI,
      timeout: 120_000,
      // M3 V8: /api/v1 is owner-gated, so e2e needs a real session. E2E_AUTH_BYPASS
      // mounts POST /auth/test-login (session-mint seam, never in prod); API_TOKENS
      // gives the cleanup helpers a SERVICE bearer to delete across users. Merged
      // over process.env, so the CI job's DATABASE_URL is preserved.
      env: {
        E2E_AUTH_BYPASS: "1",
        API_TOKENS: "e2e-service-token",
      },
    },
    {
      command: "npm run dev",
      port: 5173,
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
