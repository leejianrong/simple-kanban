<script lang="ts">
  import { board, cardsFor, COLUMNS, refetch, viewStore } from "../board.svelte";
  import Column from "./Column.svelte";
  import ViewSwitcher from "./ViewSwitcher.svelte";
  import BoardTable from "./BoardTable.svelte";
</script>

{#if board.error}
  <div class="banner error" role="alert">
    <span>{board.error}</span>
    <button onclick={refetch}>Retry</button>
  </div>
{/if}

<ViewSwitcher />

{#if board.loading && board.cards.length === 0}
  <p class="hint">Loading…</p>
{/if}

{#if viewStore.mode === "table"}
  <BoardTable />
{:else}
  <div class="board">
    {#each COLUMNS as col (col.key)}
      <Column column={col.key} label={col.label} cards={cardsFor(col.key)} />
    {/each}
  </div>
{/if}
