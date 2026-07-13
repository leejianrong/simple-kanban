// Board-membership state as Svelte 5 runes (KAN-14, wiring the KAN-12 API).
// Members are board-scoped, so the store keys off the active board (board.svelte.ts).
// Server state is authoritative — every mutation refetches, matching the board's
// no-optimistic-UI convention. Mutations throw ApiError; the Members view catches
// them to surface 404 (user unknown) / 409 (duplicate) / 403 (not owner) to the user.

import { addMember, listMembers, removeMember, updateMember, type Member, type Role } from "./api";
import { boardStore } from "./board.svelte";

export const memberStore = $state<{
  members: Member[];
  loading: boolean;
  error: string | null;
}>({ members: [], loading: false, error: null });

export async function refetchMembers(): Promise<void> {
  const boardId = boardStore.activeBoardId;
  memberStore.error = null;
  if (boardId == null) {
    memberStore.members = [];
    return;
  }
  memberStore.loading = true;
  try {
    memberStore.members = await listMembers(boardId);
  } catch (e) {
    memberStore.error = e instanceof Error ? e.message : "Failed to load members";
  } finally {
    memberStore.loading = false;
  }
}

export async function inviteMember(email: string, role: Role): Promise<void> {
  const boardId = boardStore.activeBoardId;
  if (boardId == null) return;
  await addMember(boardId, { email, role });
  await refetchMembers();
}

export async function changeMemberRole(memberId: number, role: Role): Promise<void> {
  const boardId = boardStore.activeBoardId;
  if (boardId == null) return;
  await updateMember(boardId, memberId, { role });
  await refetchMembers();
}

export async function kickMember(memberId: number): Promise<void> {
  const boardId = boardStore.activeBoardId;
  if (boardId == null) return;
  await removeMember(boardId, memberId);
  await refetchMembers();
}
