<script lang="ts">
  // Agent personal-access-token management (M3 V9, ADR 0014): create a named
  // token (secret revealed once), see your tokens' metadata, and revoke them.
  import { Plus, Trash2 } from "lucide-svelte";
  import {
    addToken,
    dismissRevealed,
    refetchTokens,
    removeToken,
    tokenStore,
  } from "../tokens.svelte";

  let adding = $state(false);
  let name = $state("");
  let busy = $state(false);
  let confirmingId = $state<number | null>(null);
  let copied = $state(false);

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    busy = true;
    try {
      await addToken(trimmed);
      name = "";
      adding = false;
    } finally {
      busy = false;
    }
  }

  async function copySecret(secret: string) {
    try {
      await navigator.clipboard.writeText(secret);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      /* clipboard may be unavailable; the secret is visible to copy manually */
    }
  }

  async function revoke(id: number) {
    if (busy) return;
    busy = true;
    try {
      await removeToken(id);
      confirmingId = null;
    } finally {
      busy = false;
    }
  }

  function fmt(iso: string | null): string {
    if (!iso) return "never";
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }
</script>

<div class="tokens-view">
  {#if tokenStore.error}
    <div class="banner error" role="alert">
      <span>{tokenStore.error}</span>
      <button onclick={refetchTokens}>Retry</button>
    </div>
  {/if}

  <div class="epics-head">
    <h2>Agent tokens</h2>
    {#if !adding}
      <button class="btn-add" onclick={() => (adding = true)}>
        <Plus size={15} /> New token
      </button>
    {/if}
  </div>

  <p class="hint">
    A token lets an agent (e.g. the MCP server) act as you — it can reach the same
    boards you can. The secret is shown once; store it somewhere safe.
  </p>

  {#if adding}
    <form
      class="card-form"
      onsubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <input
        placeholder="Token name (required)"
        aria-label="Token name"
        bind:value={name}
      />
      <div class="row actions">
        <button type="submit" class="primary" disabled={!name.trim() || busy}>Create</button>
        <button type="button" class="link" onclick={() => (adding = false)}>Cancel</button>
      </div>
    </form>
  {/if}

  {#if tokenStore.revealed}
    <div class="token-reveal" role="alert">
      <p class="token-reveal-title">
        Copy your new token <strong>{tokenStore.revealed.name}</strong> now — it won't be shown again.
      </p>
      <div class="token-reveal-row">
        <code class="secret">{tokenStore.revealed.token}</code>
        <button class="primary" onclick={() => copySecret(tokenStore.revealed!.token)}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <button class="link" onclick={dismissRevealed}>Done</button>
    </div>
  {/if}

  {#if tokenStore.loading && tokenStore.tokens.length === 0}
    <p class="hint">Loading…</p>
  {:else if tokenStore.tokens.length === 0}
    <p class="empty">No tokens yet. Create one to let an agent work on your boards.</p>
  {/if}

  <div class="epics-list">
    {#each tokenStore.tokens as token (token.id)}
      <div class="token-row card">
        <div class="token-main">
          <span class="token-name">{token.name}</span>
          <code class="token-prefix">{token.token_prefix}…</code>
        </div>
        <div class="token-meta">
          <span>created {fmt(token.created_at)}</span>
          <span>last used {fmt(token.last_used_at)}</span>
          <span>expires {fmt(token.expires_at)}</span>
        </div>
        {#if confirmingId === token.id}
          <div class="token-actions">
            <span class="confirm-msg">Revoke “{token.name}”?</span>
            <button class="danger" onclick={() => revoke(token.id)} disabled={busy}>Revoke</button>
            <button class="link" onclick={() => (confirmingId = null)}>Cancel</button>
          </div>
        {:else}
          <div class="token-actions">
            <button
              class="btn-inline-danger"
              aria-label="Revoke"
              onclick={() => (confirmingId = token.id)}
            >
              <Trash2 size={14} /> Revoke
            </button>
          </div>
        {/if}
      </div>
    {/each}
  </div>
</div>
