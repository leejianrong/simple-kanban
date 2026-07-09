// Agent-token state as Svelte 5 runes (M3 V9, ADR 0014).
// Tokens are user-scoped (not board-scoped), so they live in their own store,
// loaded when the Tokens view opens. Server state is authoritative — every
// mutation refetches, matching the board's no-optimistic-UI convention.

import {
  createToken,
  deleteToken,
  listTokens,
  type Token,
  type TokenCreated,
} from "./api";

export const tokenStore = $state<{
  tokens: Token[];
  loading: boolean;
  error: string | null;
  // The most recently created token's raw secret — shown once, then dismissed.
  // Never persisted; lives only in memory for the current session.
  revealed: TokenCreated | null;
}>({ tokens: [], loading: false, error: null, revealed: null });

export async function refetchTokens(): Promise<void> {
  tokenStore.loading = true;
  tokenStore.error = null;
  try {
    tokenStore.tokens = await listTokens();
  } catch (e) {
    tokenStore.error = e instanceof Error ? e.message : "Failed to load tokens";
  } finally {
    tokenStore.loading = false;
  }
}

export async function addToken(name: string): Promise<void> {
  const created = await createToken({ name });
  tokenStore.revealed = created; // reveal the secret once
  await refetchTokens();
}

export function dismissRevealed(): void {
  tokenStore.revealed = null;
}

export async function removeToken(id: number): Promise<void> {
  await deleteToken(id);
  // If the revealed token was the one just revoked, clear the reveal too.
  if (tokenStore.revealed?.id === id) tokenStore.revealed = null;
  await refetchTokens();
}
