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
  board_id: number;
  title: string;
  description: string | null;
  column: Column;
  position: number;
  story_points: number | null;
  assignee: string | null;
  epic_id: number | null;
  // Card-to-card dependencies (KAN-28/KAN-30): ids of cards that block this one
  // (blocked_by) and ids of cards this one blocks (blocks). `blocked` is the
  // derived signal — true when >=1 blocker is not yet done (KAN-29).
  blocked_by: number[];
  blocks: number[];
  blocked: boolean;
  // Work-links (KAN-32/KAN-34): PR / branch / CI URLs, inlined on every card read.
  links: CardLink[];
  created_at: string;
  updated_at: string;
}

// A work-link on a card (KAN-32): a label (e.g. "PR", "branch", "CI") + a url.
export interface CardLink {
  id: number;
  label: string;
  url: string;
  created_at: string;
}

// A note/comment on a card (KAN-33): a body authored by a user. Not inlined on
// card reads — fetched on demand via listComments. `author_id` is null once the
// authoring user is deleted (SET NULL).
export interface Comment {
  id: number;
  body: string;
  author_id: string | null;
  created_at: string;
}

export interface CardCreate {
  title: string;
  description?: string | null;
  column?: Column;
  story_points?: number | null;
  assignee?: string | null;
  epic_id?: number | null;
  board_id?: number;
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

// An epic is a grouping a story can belong to (ADR 0009), scoped to a board (V7).
export interface Epic {
  id: number;
  ticket_number: string;
  board_id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface EpicCreate {
  name: string;
  description?: string | null;
  board_id?: number;
}

// A board owns a set of cards + epics (M3 V7). owner_id is a user UUID or null.
export interface Board {
  id: number;
  name: string;
  owner_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface BoardCreate {
  name: string;
}

export interface BoardUpdate {
  name?: string;
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

export async function listCards(boardId?: number): Promise<Card[]> {
  const qs = boardId != null ? `?board_id=${boardId}` : "";
  const res = await fetch(`${API}/cards${qs}`);
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

// --- Card dependencies (KAN-28 API, surfaced in the UI by KAN-30) -----------
// `addDependency(cardId, blockerId)` records that `cardId` is blocked-by
// `blockerId`; `removeDependency` clears that edge. Both return the (refreshed)
// blocked card. The server enforces same-board / no-self / no-dup / no-cycle
// (422) and owner-gating — surfaced via ApiError like every other call.

export async function addDependency(cardId: number, blockerId: number): Promise<Card> {
  const res = await fetch(`${API}/cards/${cardId}/dependencies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocker_id: blockerId }),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function removeDependency(cardId: number, blockerId: number): Promise<Card> {
  const res = await fetch(`${API}/cards/${cardId}/dependencies/${blockerId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

// --- Card work-links (KAN-32 API, surfaced in the UI by KAN-34) -------------
// `addLink` attaches a label+url to a card; `removeLink` detaches one by id. Both
// return the (refreshed) card with its `links` array. Owner-gated like every call.

export async function addLink(cardId: number, label: string, url: string): Promise<Card> {
  const res = await fetch(`${API}/cards/${cardId}/links`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, url }),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function removeLink(cardId: number, linkId: number): Promise<Card> {
  const res = await fetch(`${API}/cards/${cardId}/links/${linkId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

// --- Card notes / comments (KAN-33 API, surfaced in the UI by KAN-34) --------
// Comments are a thread, so unlike links they aren't inlined on card reads —
// `listComments` fetches them on demand (oldest-first). `addComment` posts one
// (author is the session user); `deleteComment` removes your own (403 otherwise).

export async function listComments(cardId: number): Promise<Comment[]> {
  const res = await fetch(`${API}/cards/${cardId}/comments`);
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function addComment(cardId: number, body: string): Promise<Comment> {
  const res = await fetch(`${API}/cards/${cardId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function deleteComment(cardId: number, commentId: number): Promise<void> {
  const res = await fetch(`${API}/cards/${cardId}/comments/${commentId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

export async function listEpics(boardId?: number): Promise<Epic[]> {
  const qs = boardId != null ? `?board_id=${boardId}` : "";
  const res = await fetch(`${API}/epics${qs}`);
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

// --- Boards (Milestone 3 V7, ADR 0012) -------------------------------------

export async function listBoards(): Promise<Board[]> {
  const res = await fetch(`${API}/boards`);
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function createBoard(payload: BoardCreate): Promise<Board> {
  const res = await fetch(`${API}/boards`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function updateBoard(id: number, payload: BoardUpdate): Promise<Board> {
  const res = await fetch(`${API}/boards/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function deleteBoard(id: number): Promise<void> {
  const res = await fetch(`${API}/boards/${id}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

// --- Agent tokens (Milestone 3 V9, ADR 0014) -------------------------------
// Self-serve personal access tokens: a token acts as its owning user (inherits
// board access). The secret is returned exactly once, on create.

export interface Token {
  id: number;
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

// The create response — metadata plus the raw secret (shown once, never again).
export interface TokenCreated extends Token {
  token: string;
}

export interface TokenCreate {
  name: string;
  expires_at?: string | null;
}

export async function listTokens(): Promise<Token[]> {
  const res = await fetch(`${API}/tokens`);
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function createToken(payload: TokenCreate): Promise<TokenCreated> {
  const res = await fetch(`${API}/tokens`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}

export async function deleteToken(id: number): Promise<void> {
  const res = await fetch(`${API}/tokens/${id}`, { method: "DELETE" });
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
