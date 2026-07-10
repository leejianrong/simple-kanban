<script lang="ts">
  import { Plus } from "lucide-svelte";
  import { cardsForEpic, epicStore, refetchEpics } from "../board.svelte";
  import EpicForm from "./EpicForm.svelte";
  import EpicItem from "./EpicItem.svelte";

  let adding = $state(false);

  // Grouping (server-authoritative via the store): an epic is "Completed" iff it
  // has ≥1 story AND every story is in the done column. Everything else — including
  // epics with no stories yet — is "Active".
  function isCompleted(epicId: number): boolean {
    const s = cardsForEpic(epicId);
    return s.length > 0 && s.every((c) => c.column === "done");
  }
  const activeEpics = $derived(epicStore.epics.filter((e) => !isCompleted(e.id)));
  const completedEpics = $derived(epicStore.epics.filter((e) => isCompleted(e.id)));
</script>

<div class="epics-view page-view">
  {#if epicStore.error}
    <div class="banner error" role="alert">
      <span>{epicStore.error}</span>
      <button onclick={refetchEpics}>Retry</button>
    </div>
  {/if}

  <div class="page-head">
    <div>
      <h2>Epics</h2>
      <p class="page-sub">Group related stories and track them to done.</p>
    </div>
    {#if !adding}
      <button class="btn-add" onclick={() => (adding = true)}>
        <Plus size={15} /> New epic
      </button>
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

  {#if activeEpics.length > 0}
    <div class="section-head">
      <span class="section-dot active" aria-hidden="true"></span>
      <span class="section-label">Active</span>
      <span class="section-count">{activeEpics.length}</span>
      <span class="section-rule"></span>
    </div>
    <div class="epic-grid">
      {#each activeEpics as epic (epic.id)}
        <EpicItem {epic} />
      {/each}
    </div>
  {/if}

  {#if completedEpics.length > 0}
    <div class="section-head">
      <span class="section-dot done" aria-hidden="true"></span>
      <span class="section-label">Completed</span>
      <span class="section-count">{completedEpics.length}</span>
      <span class="section-rule"></span>
    </div>
    <div class="epic-grid">
      {#each completedEpics as epic (epic.id)}
        <EpicItem {epic} />
      {/each}
    </div>
  {/if}
</div>
