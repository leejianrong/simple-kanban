// Board state as Svelte 5 runes (SHAPING §Board state).
// After every mutation we refetch GET /api/cards; the server state is
// authoritative — no optimistic UI (BREADBOARD §7).

import {
  addDependency,
  addLink,
  createBoard,
  createCard,
  createEpic,
  createLabel,
  deleteBoard,
  deleteCard,
  deleteEpic,
  deleteLabel,
  listBoards,
  listCards,
  listEpics,
  listLabels,
  moveCard as apiMoveCard,
  removeDependency,
  removeLink,
  updateBoard,
  updateCard,
  updateEpic,
  type Board,
  type Card,
  type CardCreate,
  type CardMove,
  type CardUpdate,
  type Column,
  type Epic,
  type EpicCreate,
  type EpicUpdate,
  type Label,
} from "./api";

export const COLUMNS: { key: Column; label: string }[] = [
  { key: "todo", label: "Todo" },
  { key: "in_progress", label: "In Progress" },
  { key: "done", label: "Done" },
];

// Boards (M3 V7). The active board scopes the card/epic views + creates. Its id is
// persisted per-browser so a reload keeps you on the same board.
export const boardStore = $state<{
  boards: Board[];
  activeBoardId: number | null;
  loading: boolean;
  error: string | null;
}>({ boards: [], activeBoardId: null, loading: false, error: null });

const ACTIVE_BOARD_KEY = "kanban.activeBoardId";

function persistActiveBoard(id: number | null): void {
  if (typeof localStorage === "undefined") return;
  if (id == null) localStorage.removeItem(ACTIVE_BOARD_KEY);
  else localStorage.setItem(ACTIVE_BOARD_KEY, String(id));
}

function readPersistedActiveBoard(): number | null {
  if (typeof localStorage === "undefined") return null;
  const raw = localStorage.getItem(ACTIVE_BOARD_KEY);
  return raw ? Number(raw) : null;
}

export function activeBoard(): Board | null {
  return boardStore.boards.find((b) => b.id === boardStore.activeBoardId) ?? null;
}

// Load the board list and resolve which one is active: keep the current selection
// if it still exists, else the persisted one, else the first board. Does NOT load
// cards/epics — callers pair this with refetch()/refetchEpics() (or setActiveBoard).
export async function refetchBoards(): Promise<void> {
  boardStore.loading = true;
  boardStore.error = null;
  try {
    const boards = await listBoards();
    boardStore.boards = boards;
    const ids = new Set(boards.map((b) => b.id));
    let active = boardStore.activeBoardId;
    if (active == null || !ids.has(active)) active = readPersistedActiveBoard();
    if (active == null || !ids.has(active)) active = boards[0]?.id ?? null;
    boardStore.activeBoardId = active;
    persistActiveBoard(active);
  } catch (e) {
    boardStore.error = e instanceof Error ? e.message : "Failed to load boards";
  } finally {
    boardStore.loading = false;
  }
}

// Switch the active board and load its cards + epics + labels.
export async function setActiveBoard(id: number): Promise<void> {
  boardStore.activeBoardId = id;
  persistActiveBoard(id);
  await Promise.all([refetch(), refetchEpics(), refetchLabels()]);
}

export async function addBoard(name: string): Promise<void> {
  const created = await createBoard({ name });
  await refetchBoards();
  await setActiveBoard(created.id); // creating a board switches to it
}

export async function editBoard(id: number, name: string): Promise<void> {
  await updateBoard(id, { name });
  await refetchBoards();
}

export async function removeBoard(id: number): Promise<void> {
  await deleteBoard(id);
  // If the active board was deleted, drop the selection so refetchBoards picks a
  // new one (its cards/epics were cascade-deleted server-side).
  if (boardStore.activeBoardId === id) boardStore.activeBoardId = null;
  await refetchBoards();
  await Promise.all([refetch(), refetchEpics(), refetchLabels()]);
}

// A single reactive object; we mutate its properties (never reassign the export).
export const board = $state<{
  cards: Card[];
  loading: boolean;
  error: string | null;
}>({
  cards: [],
  loading: false,
  error: null,
});

export function cardsFor(column: Column): Card[] {
  return board.cards
    .filter((c) => c.column === column)
    .sort((a, b) => a.position - b.position);
}

// A card by id, for rendering dependency references (blocked_by / blocks) by
// their ticket number + title (KAN-30). Null if it isn't in the loaded board —
// callers fall back to a bare id.
export function cardById(id: number): Card | null {
  return board.cards.find((c) => c.id === id) ?? null;
}

// Epics live in their own store (they are not board cards — ADR 0009). Loaded
// alongside cards so both the Board (story epic-tags) and the Epics view can read
// them.
export const epicStore = $state<{
  epics: Epic[];
  loading: boolean;
  error: string | null;
}>({
  epics: [],
  loading: false,
  error: null,
});

// The epic a story belongs to (for its card-face tag), or null.
export function epicFor(id: number | null): Epic | null {
  if (id == null) return null;
  return epicStore.epics.find((e) => e.id === id) ?? null;
}

// Stories that belong to a given epic (for the Epics-view rollup).
export function cardsForEpic(epicId: number): Card[] {
  return board.cards.filter((c) => c.epic_id === epicId);
}

export async function refetch(): Promise<void> {
  board.loading = true;
  board.error = null;
  try {
    // Scope to the active board; with none selected there's nothing to show.
    board.cards =
      boardStore.activeBoardId == null ? [] : await listCards(boardStore.activeBoardId);
  } catch (e) {
    board.error = e instanceof Error ? e.message : "Failed to load cards";
  } finally {
    board.loading = false;
  }
}

export async function addCard(payload: CardCreate): Promise<void> {
  await createCard({ ...payload, board_id: boardStore.activeBoardId ?? undefined });
  await refetch();
}

export async function editCard(id: number, payload: CardUpdate): Promise<void> {
  await updateCard(id, payload);
  await refetch();
}

export async function removeCard(id: number): Promise<void> {
  await deleteCard(id);
  await refetch();
}

// Dependency edits (KAN-30). Like every other mutation these are
// server-authoritative: the endpoint enforces the same-board / no-cycle rules
// and we refetch() to pick up the refreshed blocked_by/blocks/blocked on every
// affected card (a blocker moving in/out of a card also flips `blocked`).
export async function addBlocker(cardId: number, blockerId: number): Promise<void> {
  await addDependency(cardId, blockerId);
  await refetch();
}

export async function removeBlocker(cardId: number, blockerId: number): Promise<void> {
  await removeDependency(cardId, blockerId);
  await refetch();
}

// Work-link edits (KAN-34). Links are inlined on every card read, so like the
// other mutations these are server-authoritative: add/remove then refetch() to
// pick up the card's refreshed `links` array.
export async function addCardLink(
  cardId: number,
  label: string,
  url: string,
): Promise<void> {
  await addLink(cardId, label, url);
  await refetch();
}

export async function removeCardLink(cardId: number, linkId: number): Promise<void> {
  await removeLink(cardId, linkId);
  await refetch();
}

export async function moveCard(id: number, payload: CardMove): Promise<void> {
  // Unlike the other mutations, a drag has already changed the board visually
  // (svelte-dnd-action reorders optimistically). So on failure we must refetch
  // to snap back to the authoritative server order, then surface the error —
  // refetch() clears board.error, so set it afterwards (BREADBOARD §7).
  try {
    await apiMoveCard(id, payload);
    await refetch();
  } catch (e) {
    await refetch();
    board.error = e instanceof Error ? e.message : "Failed to move card";
  }
}

export async function refetchEpics(): Promise<void> {
  epicStore.loading = true;
  epicStore.error = null;
  try {
    epicStore.epics =
      boardStore.activeBoardId == null ? [] : await listEpics(boardStore.activeBoardId);
  } catch (e) {
    epicStore.error = e instanceof Error ? e.message : "Failed to load epics";
  } finally {
    epicStore.loading = false;
  }
}

export async function addEpic(payload: EpicCreate): Promise<void> {
  await createEpic({ ...payload, board_id: boardStore.activeBoardId ?? undefined });
  await refetchEpics();
}

export async function editEpic(id: number, payload: EpicUpdate): Promise<void> {
  await updateEpic(id, payload);
  await refetchEpics();
}

export async function removeEpic(id: number): Promise<void> {
  await deleteEpic(id);
  // Deleting an epic detaches its stories server-side (epic_id → null), so
  // refetch cards too to drop their now-stale epic tags.
  await Promise.all([refetchEpics(), refetch()]);
}

// Labels live in their own store (M5 V11, KAN-244) — board-scoped, colored tags
// the CardForm/CardModal multi-select reads and each Card renders as chips. Loaded
// alongside cards + epics so a card's inlined `labels` and the picker stay in step.
export const labelStore = $state<{
  labels: Label[];
  loading: boolean;
  error: string | null;
}>({ labels: [], loading: false, error: null });

export async function refetchLabels(): Promise<void> {
  labelStore.loading = true;
  labelStore.error = null;
  try {
    labelStore.labels =
      boardStore.activeBoardId == null ? [] : await listLabels(boardStore.activeBoardId);
  } catch (e) {
    labelStore.error = e instanceof Error ? e.message : "Failed to load labels";
  } finally {
    labelStore.loading = false;
  }
}

// Create a label on the active board, then refetch the label list (server
// authoritative). Returns the created label so a caller can attach it immediately.
export async function addLabel(name: string, color: string): Promise<Label | null> {
  if (boardStore.activeBoardId == null) return null;
  const created = await createLabel(boardStore.activeBoardId, { name, color });
  await refetchLabels();
  return created;
}

// Delete a label board-wide; it detaches from every card server-side (cascade),
// so refetch cards too to drop the now-stale chips.
export async function removeLabel(id: number): Promise<void> {
  await deleteLabel(id);
  await Promise.all([refetchLabels(), refetch()]);
}
