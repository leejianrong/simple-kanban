// Board state as Svelte 5 runes (SHAPING §Board state).
// After every mutation we refetch GET /api/cards; the server state is
// authoritative — no optimistic UI (BREADBOARD §7).

import {
  createBoard,
  createCard,
  createEpic,
  deleteBoard,
  deleteCard,
  deleteEpic,
  listBoards,
  listCards,
  listEpics,
  moveCard as apiMoveCard,
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

// Switch the active board and load its cards + epics.
export async function setActiveBoard(id: number): Promise<void> {
  boardStore.activeBoardId = id;
  persistActiveBoard(id);
  await Promise.all([refetch(), refetchEpics()]);
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
  await Promise.all([refetch(), refetchEpics()]);
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
