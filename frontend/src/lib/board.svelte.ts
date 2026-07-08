// Board state as Svelte 5 runes (SHAPING §Board state).
// After every mutation we refetch GET /api/cards; the server state is
// authoritative — no optimistic UI (BREADBOARD §7).

import {
  createCard,
  createEpic,
  deleteCard,
  deleteEpic,
  listCards,
  listEpics,
  moveCard as apiMoveCard,
  updateCard,
  updateEpic,
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
    board.cards = await listCards();
  } catch (e) {
    board.error = e instanceof Error ? e.message : "Failed to load cards";
  } finally {
    board.loading = false;
  }
}

export async function addCard(payload: CardCreate): Promise<void> {
  await createCard(payload);
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
    epicStore.epics = await listEpics();
  } catch (e) {
    epicStore.error = e instanceof Error ? e.message : "Failed to load epics";
  } finally {
    epicStore.loading = false;
  }
}

export async function addEpic(payload: EpicCreate): Promise<void> {
  await createEpic(payload);
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
