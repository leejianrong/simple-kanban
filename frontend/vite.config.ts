import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Dev server proxies to the FastAPI backend so dev mirrors the same-origin
// production setup and needs no CORS (ADR 0008). Prod is served by FastAPI itself.
// /auth and /users are the fastapi-users auth + identity routes (M3 V6); they sit
// outside /api/v1 (session plumbing, like /api/health) so they need their own
// proxy entries.
export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/users": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
