<script lang="ts">
  import type { Column } from "../api";
  import { addCard, epicStore } from "../board.svelte";

  // Create-only: the add-card affordance inside a column. Editing an existing
  // card now happens in CardModal (opened from the card face), so this form no
  // longer carries the edit-only fields (blockers / links / notes / status).
  let { column, onclose }: { column: Column; onclose: () => void } = $props();

  const STORY_POINTS = [1, 2, 3, 5, 8, 13];

  let title = $state("");
  let description = $state("");
  let assignee = $state("");
  let storyPoints = $state<string>(""); // "" = unestimated
  let epicId = $state<string>(""); // "" = no epic
  let submitting = $state(false);
  let error = $state<string | null>(null);

  const epicOptions = $derived(epicStore.epics);
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
        epic_id: epicId ? Number(epicId) : null,
        column,
      });
      onclose();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to save card";
    } finally {
      submitting = false;
    }
  }
</script>

<form class="card-form" onsubmit={submit}>
  <!-- svelte-ignore a11y_autofocus -->
  <input type="text" placeholder="Title (required)" bind:value={title} autofocus />
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

  <select bind:value={epicId} aria-label="Epic">
    <option value="">— no epic</option>
    {#each epicOptions as epic (epic.id)}
      <option value={String(epic.id)}>{epic.ticket_number} · {epic.name}</option>
    {/each}
  </select>

  {#if error}
    <p class="form-error" role="alert">{error}</p>
  {/if}

  <div class="row actions">
    <button type="submit" class="primary" disabled={!canSubmit}>Create</button>
    <button type="button" onclick={onclose} disabled={submitting}>Cancel</button>
  </div>
</form>
