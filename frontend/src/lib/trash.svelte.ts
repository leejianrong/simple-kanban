// Trash view state as Svelte 5 runes (KAN-20, wiring the KAN-19 soft-delete
// tombstone + the new /trash, /restore and /purge endpoints). Board-scoped, so the
// store keys off the active board (board.svelte.ts). Server state is authoritative:
// every restore/purge re-reads the trash list, and — since a restore brings an item
// back to the live board/epics — the board + epic stores too.

import {
  listTrashCards,
  listTrashEpics,
  purgeCard,
  purgeEpic,
  restoreCard,
  restoreEpic,
  type TrashCard,
  type TrashEpic,
} from "./api";
import { boardStore, refetch, refetchEpics } from "./board.svelte";

export const trashStore = $state<{
  cards: TrashCard[];
  epics: TrashEpic[];
  loading: boolean;
  error: string | null;
}>({ cards: [], epics: [], loading: false, error: null });

// (Re)load the active board's trashed cards + epics, replacing what's shown.
export async function refetchTrash(): Promise<void> {
  const boardId = boardStore.activeBoardId;
  trashStore.error = null;
  if (boardId == null) {
    trashStore.cards = [];
    trashStore.epics = [];
    return;
  }
  trashStore.loading = true;
  try {
    const [cards, epics] = await Promise.all([
      listTrashCards(boardId),
      listTrashEpics(boardId),
    ]);
    trashStore.cards = cards;
    trashStore.epics = epics;
  } catch (e) {
    trashStore.error = e instanceof Error ? e.message : "Failed to load trash";
  } finally {
    trashStore.loading = false;
  }
}

// A restore brings the item back to a live view, so refresh those stores too.
export async function restoreCardItem(id: number): Promise<void> {
  await restoreCard(id);
  await Promise.all([refetchTrash(), refetch()]);
}

export async function restoreEpicItem(id: number): Promise<void> {
  await restoreEpic(id);
  // A restored epic re-associates its still-linked stories, so refresh cards too.
  await Promise.all([refetchTrash(), refetchEpics(), refetch()]);
}

// A purge is permanent and touches only the trash listing.
export async function purgeCardItem(id: number): Promise<void> {
  await purgeCard(id);
  await refetchTrash();
}

export async function purgeEpicItem(id: number): Promise<void> {
  await purgeEpic(id);
  // Purging an epic detaches its stories server-side (epic_id → null), so refresh
  // cards to drop any now-stale epic tags on the board.
  await Promise.all([refetchTrash(), refetch()]);
}
