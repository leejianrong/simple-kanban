// Board state as Svelte 5 runes (SHAPING §Board state).
// After every mutation we refetch GET /api/cards; the server state is
// authoritative — no optimistic UI (BREADBOARD §7).

import {
  createCard,
  deleteCard,
  listCards,
  moveCard as apiMoveCard,
  updateCard,
  type Card,
  type CardCreate,
  type CardMove,
  type CardUpdate,
  type Column,
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
