<script lang="ts">
  import { Pencil, Trash2 } from "lucide-svelte";
  import type { Epic } from "../api";
  import { cardsForEpic, removeEpic } from "../board.svelte";
  import EpicModal from "./EpicModal.svelte";

  let { epic }: { epic: Epic } = $props();

  let mode = $state<"view" | "confirmDelete">("view");
  let showModal = $state(false);
  let deleting = $state(false);
  let deleteError = $state<string | null>(null);

  // Child stories (the rollup) + done progress.
  const stories = $derived(cardsForEpic(epic.id));
  const doneCount = $derived(stories.filter((s) => s.column === "done").length);
  const pct = $derived(stories.length ? Math.round((doneCount / stories.length) * 100) : 0);
  const allDone = $derived(stories.length > 0 && doneCount === stories.length);

  function isInteractive(t: EventTarget | null): boolean {
    return t instanceof Element && !!t.closest("button, a");
  }
  function openFromClick(e: MouseEvent) {
    if (isInteractive(e.target)) return;
    showModal = true;
  }
  function onKeydown(e: KeyboardEvent) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      showModal = true;
    }
  }

  async function confirmDelete() {
    deleting = true;
    deleteError = null;
    try {
      await removeEpic(epic.id);
    } catch (e) {
      deleteError = e instanceof Error ? e.message : "Failed to delete epic";
      deleting = false;
    }
  }
</script>

{#if mode === "confirmDelete"}
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
  <div
    class="card epic-card"
    class:completed={allDone}
    role="button"
    tabindex="0"
    aria-label="Open {epic.ticket_number}: {epic.name}"
    onclick={openFromClick}
    onkeydown={onKeydown}
  >
    <div class="card-top">
      <span class="ticket epic-ticket">{epic.ticket_number}</span>
      <span class="epic-count">{stories.length} {stories.length === 1 ? "story" : "stories"}</span>
      <div class="card-actions">
        <button class="icon-btn" title="Edit" aria-label="Edit" onclick={() => (showModal = true)}>
          <Pencil size={15} />
        </button>
        <button
          class="icon-btn danger"
          title="Delete"
          aria-label="Delete"
          onclick={() => (mode = "confirmDelete")}
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
    <p class="epic-name">{epic.name}</p>
    {#if epic.description}
      <p class="epic-desc">{epic.description}</p>
    {/if}
    <div class="progress">
      <div class="bar"><i class:full={allDone} style="width:{pct}%"></i></div>
      <span class="pct">{doneCount} / {stories.length} done</span>
    </div>
    {#if stories.length > 0}
      <ul class="epic-stories">
        {#each stories as story (story.id)}
          <li class:is-done={story.column === "done"}>
            <span class="sdot {story.column}" aria-hidden="true"></span>
            <span class="ticket">{story.ticket_number}</span>
            <span class="stitle">{story.title}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

{#if showModal}
  <EpicModal epicId={epic.id} onclose={() => (showModal = false)} />
{/if}
