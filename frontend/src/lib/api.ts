// Thin typed fetch wrapper over /api (SHAPING §Frontend components).
// The UI performs no action the API can't (R4.1). Throws on non-2xx.

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
  const res = await fetch("/api/cards");
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function createCard(payload: CardCreate): Promise<Card> {
  const res = await fetch("/api/cards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function updateCard(id: number, payload: CardUpdate): Promise<Card> {
  const res = await fetch(`/api/cards/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function moveCard(id: number, payload: CardMove): Promise<Card> {
  const res = await fetch(`/api/cards/${id}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function deleteCard(id: number): Promise<void> {
  const res = await fetch(`/api/cards/${id}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

export async function listEpics(): Promise<Epic[]> {
  const res = await fetch("/api/epics");
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function createEpic(payload: EpicCreate): Promise<Epic> {
  const res = await fetch("/api/epics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function updateEpic(id: number, payload: EpicUpdate): Promise<Epic> {
  const res = await fetch(`/api/epics/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function deleteEpic(id: number): Promise<void> {
  const res = await fetch(`/api/epics/${id}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}
