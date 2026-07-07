<script lang="ts">
  import { board, cardsFor, COLUMNS, refetch } from "../board.svelte";
  import Column from "./Column.svelte";
</script>

{#if board.error}
  <div class="banner error" role="alert">
    <span>{board.error}</span>
    <button onclick={refetch}>Retry</button>
  </div>
{/if}

{#if board.loading && board.cards.length === 0}
  <p class="hint">Loading…</p>
{/if}

<div class="board">
  {#each COLUMNS as col (col.key)}
    <Column column={col.key} label={col.label} cards={cardsFor(col.key)} />
  {/each}
</div>
