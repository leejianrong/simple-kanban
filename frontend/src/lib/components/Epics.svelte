<script lang="ts">
  import { epicStore, refetchEpics } from "../board.svelte";
  import EpicForm from "./EpicForm.svelte";
  import EpicItem from "./EpicItem.svelte";

  let adding = $state(false);
</script>

<div class="epics-view">
  {#if epicStore.error}
    <div class="banner error" role="alert">
      <span>{epicStore.error}</span>
      <button onclick={refetchEpics}>Retry</button>
    </div>
  {/if}

  <div class="epics-head">
    <h2>Epics</h2>
    {#if !adding}
      <button class="add" onclick={() => (adding = true)}>+ New epic</button>
    {/if}
  </div>

  {#if adding}
    <EpicForm onclose={() => (adding = false)} />
  {/if}

  {#if epicStore.loading && epicStore.epics.length === 0}
    <p class="hint">Loading…</p>
  {:else if epicStore.epics.length === 0}
    <p class="empty">No epics yet. Create one to group related stories.</p>
  {/if}

  <div class="epics-list">
    {#each epicStore.epics as epic (epic.id)}
      <EpicItem {epic} />
    {/each}
  </div>
</div>
