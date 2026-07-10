// Light/dark theme, persisted per-browser and applied via a `data-theme`
// attribute on <html> (so both app.css and the landing's scoped tokens switch).
// The choice wins over the OS preference in both directions (app.css defines
// :root[data-theme="light"] and :root[data-theme="dark"] overrides). First load
// with nothing stored falls back to the OS preference. The index.html inline
// script sets the attribute pre-paint to avoid a flash; this store keeps the app
// reactive and owns toggling/persistence.

export type Theme = "light" | "dark";

const KEY = "kanban.theme";

function systemTheme(): Theme {
  return typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export const themeStore = $state<{ theme: Theme }>({
  theme: stored() ?? systemTheme(),
});

function apply(theme: Theme): void {
  themeStore.theme = theme;
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

// Sync the DOM attribute with the resolved theme on startup (idempotent with the
// index.html inline script).
export function initTheme(): void {
  apply(themeStore.theme);
}

export function toggleTheme(): void {
  const next: Theme = themeStore.theme === "dark" ? "light" : "dark";
  apply(next);
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* persistence may be unavailable (private mode) — the choice still applies */
  }
}
