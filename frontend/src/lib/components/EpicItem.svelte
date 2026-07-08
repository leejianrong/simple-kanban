<script lang="ts">
  import type { Epic } from "../api";
  import { cardsForEpic, removeEpic } from "../board.svelte";
  import EpicForm from "./EpicForm.svelte";

  let { epic }: { epic: Epic } = $props();

  let mode = $state<"view" | "edit" | "confirmDelete">("view");
  let deleting = $state(false);
  let deleteError = $state<string | null>(null);

  // Child stories (the rollup) — the board no longer shows epics, so this is the
  // only place their stories are visible together.
  const stories = $derived(cardsForEpic(epic.id));

  async function confirmDelete() {
    deleting = true;
    deleteError = null;
    try {
      await removeEpic(epic.id);
      // On success this epic is gone from the store and the component unmounts.
    } catch (e) {
      deleteError = e instanceof Error ? e.message : "Failed to delete epic";
      deleting = false;
    }
  }
</script>

{#if mode === "edit"}
  <EpicForm {epic} onclose={() => (mode = "view")} />
{:else if mode === "confirmDelete"}
  <div class="card confirm">
    <p class="confirm-msg">
      Delete <strong>{epic.ticket_number}</strong> — “{epic.name}”? Its
      {stories.length} linked {stories.length === 1 ? "story" : "stories"} will be unlinked
      (not deleted).
    </p>
    {#if deleteError}
      <p class="form-error" role="alert">{deleteError}</p>
    {/if}
    <div class="row actions">
      <button class="danger" onclick={confirmDelete} disabled={deleting}>Delete</button>
      <button onclick={() => (mode = "view")} disabled={deleting}>Cancel</button>
    </div>
  </div>
{:else}
  <article class="card epic-card">
    <div class="card-top">
      <span class="ticket">{epic.ticket_number}</span>
      <span class="epic-count">{stories.length} {stories.length === 1 ? "story" : "stories"}</span>
    </div>
    <p class="card-title">{epic.name}</p>
    {#if epic.description}
      <p class="epic-desc">{epic.description}</p>
    {/if}
    {#if stories.length > 0}
      <ul class="epic-stories">
        {#each stories as story (story.id)}
          <li><span class="ticket">{story.ticket_number}</span> {story.title}</li>
        {/each}
      </ul>
    {/if}
    <div class="card-actions">
      <button class="link" onclick={() => (mode = "edit")}>Edit</button>
      <button class="link danger" onclick={() => (mode = "confirmDelete")}>Delete</button>
    </div>
  </article>
{/if}
