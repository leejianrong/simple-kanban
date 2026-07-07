<script lang="ts">
  import type { Column } from "../api";
  import { addCard } from "../board.svelte";

  let { column, onclose }: { column: Column; onclose: () => void } = $props();

  const STORY_POINTS = [1, 2, 3, 5, 8, 13];

  let title = $state("");
  let description = $state("");
  let assignee = $state("");
  let storyPoints = $state<string>(""); // "" = unestimated
  let submitting = $state(false);
  let error = $state<string | null>(null);

  const canSubmit = $derived(title.trim().length > 0 && !submitting);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    submitting = true;
    error = null;
    try {
      await addCard({
        title: title.trim(),
        description: description.trim() || null,
        assignee: assignee.trim() || null,
        story_points: storyPoints ? Number(storyPoints) : null,
        column,
      });
      onclose();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to create card";
    } finally {
      submitting = false;
    }
  }
</script>

<form class="card-form" onsubmit={submit}>
  <!-- svelte-ignore a11y_autofocus -->
  <input
    type="text"
    placeholder="Title (required)"
    bind:value={title}
    autofocus
  />
  <textarea placeholder="Description (optional)" rows="2" bind:value={description}
  ></textarea>
  <div class="row">
    <input type="text" placeholder="Assignee" bind:value={assignee} />
    <select bind:value={storyPoints} aria-label="Story points">
      <option value="">— pts</option>
      {#each STORY_POINTS as p}
        <option value={String(p)}>{p}</option>
      {/each}
    </select>
  </div>

  {#if error}
    <p class="form-error" role="alert">{error}</p>
  {/if}

  <div class="row actions">
    <button type="submit" class="primary" disabled={!canSubmit}>Create</button>
    <button type="button" onclick={onclose}>Cancel</button>
  </div>
</form>
