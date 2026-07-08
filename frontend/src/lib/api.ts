// Thin typed fetch wrapper over /api (SHAPING §Frontend components).
// The UI performs no action the API can't (R4.1). Throws on non-2xx.

export type Column = "todo" | "in_progress" | "done";
export type Kind = "epic" | "story";

export interface Card {
  id: number;
  ticket_number: string;
  title: string;
  description: string | null;
  column: Column;
  position: number;
  story_points: number | null;
  assignee: string | null;
  kind: Kind;
  parent_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface CardCreate {
  title: string;
  description?: string | null;
  column?: Column;
  story_points?: number | null;
  assignee?: string | null;
  kind?: Kind;
  parent_id?: number | null;
}

// Field edits only — no column (moving is done via /move, not PATCH). `kind` is
// fixed at creation; only `parent_id` (re-parent a story) is editable here.
export interface CardUpdate {
  title?: string;
  description?: string | null;
  story_points?: number | null;
  assignee?: string | null;
  parent_id?: number | null;
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
