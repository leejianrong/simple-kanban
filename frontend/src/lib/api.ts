// Thin typed fetch wrapper over the versioned API (SHAPING §Frontend components).
// The UI performs no action the API can't (R4.1). Throws on non-2xx.
//
// All calls go through the canonical /api/v1 prefix (P3, milestone-2 V2). The
// backend also serves a temporary /api alias, but the SPA rides the versioned path.
const API = "/api/v1";

export type Column = "todo" | "in_progress" | "done";

export interface Card {
  id: number;
  ticket_number: string;
  title: string;
  description: string | null;
  column: Column;
  position: number;
  story_points: number | null;
  assignee: string | null;
  epic_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface CardCreate {
  title: string;
  description?: string | null;
  column?: Column;
  story_points?: number | null;
  assignee?: string | null;
  epic_id?: number | null;
}

// Field edits only — no column (moving is done via /move, not PATCH).
// `epic_id` re-links the story to a different epic (or null to clear).
export interface CardUpdate {
  title?: string;
  description?: string | null;
  story_points?: number | null;
  assignee?: string | null;
  epic_id?: number | null;
}

// An epic is a board-less grouping a story can belong to (ADR 0009).
export interface Epic {
  id: number;
  ticket_number: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface EpicCreate {
  name: string;
  description?: string | null;
}

export interface EpicUpdate {
  name?: string;
  description?: string | null;
}

export interface CardMove {
  column: Column;
  position?: number | null;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail) return JSON.stringify(body.detail);
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status})`;
}

export async function listCards(): Promise<Card[]> {
  const res = await fetch(`${API}/cards`);
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function createCard(payload: CardCreate): Promise<Card> {
  const res = await fetch(`${API}/cards`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function updateCard(id: number, payload: CardUpdate): Promise<Card> {
  const res = await fetch(`${API}/cards/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function moveCard(id: number, payload: CardMove): Promise<Card> {
  const res = await fetch(`${API}/cards/${id}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function deleteCard(id: number): Promise<void> {
  const res = await fetch(`${API}/cards/${id}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

export async function listEpics(): Promise<Epic[]> {
  const res = await fetch(`${API}/epics`);
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function createEpic(payload: EpicCreate): Promise<Epic> {
  const res = await fetch(`${API}/epics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function updateEpic(id: number, payload: EpicUpdate): Promise<Epic> {
  const res = await fetch(`${API}/epics/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function deleteEpic(id: number): Promise<void> {
  const res = await fetch(`${API}/epics/${id}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

// --- Auth (Milestone 3 V6, ADR 0011) ---------------------------------------
// The fastapi-users auth + identity routes live at the origin root (/auth,
// /users), NOT under /api/v1 — they're session plumbing, so no API prefix.

export interface CurrentUser {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
}

// The signed-in user, or null when logged out (401). The app-shell auth check.
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const res = await fetch("/users/me");
  if (res.status === 401) return null;
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function logout(): Promise<void> {
  const res = await fetch("/auth/logout", { method: "POST" });
  // 204 on success; 401 means the session was already gone — both are "logged out".
  if (!res.ok && res.status !== 401) throw new ApiError(res.status, await parseError(res));
}

// The GitHub authorize endpoint returns JSON `{ authorization_url }` rather than a
// redirect, so we fetch it and then navigate the browser there (ADR 0011). On the
// return trip the backend sets the session cookie and redirects to `/`.
export async function startGitHubLogin(): Promise<void> {
  const res = await fetch("/auth/github/authorize");
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  const { authorization_url } = await res.json();
  window.location.href = authorization_url;
}
