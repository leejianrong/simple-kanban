// Board activity-feed state as Svelte 5 runes (KAN-18, wiring the KAN-17 write
// path + the new GET /boards/{id}/activity read API). The feed is board-scoped, so
// the store keys off the active board (board.svelte.ts). Server state is
// authoritative — this is read-only (there is no activity mutation); the panel just
// (re)loads and pages. Mutations elsewhere in the app record activity server-side,
// so a Refresh re-reads the newest rows.

import { listActivity, type Activity } from "./api";
import { boardStore } from "./board.svelte";

// How many rows a page fetches (both the initial load and each "Load more").
const PAGE_SIZE = 25;

export const activityStore = $state<{
  entries: Activity[];
  cursor: string | null; // next-page cursor (null → no more / not loaded)
  loading: boolean;
  error: string | null;
}>({ entries: [], cursor: null, loading: false, error: null });

// (Re)load the first, newest page for the active board, replacing what's shown.
export async function refetchActivity(): Promise<void> {
  const boardId = boardStore.activeBoardId;
  activityStore.error = null;
  if (boardId == null) {
    activityStore.entries = [];
    activityStore.cursor = null;
    return;
  }
  activityStore.loading = true;
  try {
    const page = await listActivity(boardId, { limit: PAGE_SIZE });
    activityStore.entries = page.entries;
    activityStore.cursor = page.nextCursor;
  } catch (e) {
    activityStore.error = e instanceof Error ? e.message : "Failed to load activity";
  } finally {
    activityStore.loading = false;
  }
}

// Append the next (older) page, following the keyset cursor. No-op on the last page.
export async function loadMoreActivity(): Promise<void> {
  const boardId = boardStore.activeBoardId;
  if (boardId == null || activityStore.cursor == null || activityStore.loading) return;
  activityStore.loading = true;
  activityStore.error = null;
  try {
    const page = await listActivity(boardId, {
      limit: PAGE_SIZE,
      cursor: activityStore.cursor,
    });
    activityStore.entries = [...activityStore.entries, ...page.entries];
    activityStore.cursor = page.nextCursor;
  } catch (e) {
    activityStore.error = e instanceof Error ? e.message : "Failed to load activity";
  } finally {
    activityStore.loading = false;
  }
}
