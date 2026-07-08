<script lang="ts">
  import { untrack } from "svelte";
  import type { Card, Column, Kind } from "../api";
  import { addCard, editCard, epics } from "../board.svelte";

  // Create mode: pass `column`. Edit mode: pass `card` (P3). `onrequestdelete`
  // is shown only in edit mode and routes to the delete confirmation (P4).
  let {
    column,
    card,
    onclose,
    onrequestdelete,
  }: {
    column?: Column;
    card?: Card;
    onclose: () => void;
    onrequestdelete?: () => void;
  } = $props();

  const STORY_POINTS = [1, 2, 3, 5, 8, 13];

  // A form instance is create-or-edit for its whole lifetime, so snapshot the
  // mode and the initial (normalized) field values once. untrack() makes the
  // one-time read explicit — the form must not reset itself if board state
  // refetches while it's open. The initials also drive change detection.
  const { isEdit, iTitle, iDesc, iAssignee, iPts } = untrack(() => ({
    isEdit: !!card,
    iTitle: card?.title ?? "",
    iDesc: card?.description ?? "",
    iAssignee: card?.assignee ?? "",
    iPts: card?.story_points != null ? String(card.story_points) : "",
  }));

  let title = $state(iTitle);
  let description = $state(iDesc);
  let assignee = $state(iAssignee);
  let storyPoints = $state<string>(iPts); // "" = unestimated
  let submitting = $state(false);
  let error = $state<string | null>(null);

  // Kind + parent are set only at creation (kind is not editable via PATCH).
  let kind = $state<Kind>("story");
  let parentId = $state<string>(""); // "" = no parent epic
  // The epics a new story can be parented under.
  const parentOptions = $derived(epics());

  const dirty = $derived(
    title.trim() !== iTitle ||
      description.trim() !== iDesc ||
      assignee.trim() !== iAssignee ||
      storyPoints !== iPts,
  );
  // Create is always submittable once titled; Edit also needs a change.
  const canSubmit = $derived(
    title.trim().length > 0 && (!isEdit || dirty) && !submitting,
  );

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    submitting = true;
    error = null;
    const fields = {
      title: title.trim(),
      description: description.trim() || null,
      assignee: assignee.trim() || null,
      story_points: storyPoints ? Number(storyPoints) : null,
    };
    try {
      if (isEdit) {
        await editCard(card!.id, fields);
      } else {
        await addCard({
          ...fields,
          column: column!,
          kind,
          parent_id: kind === "story" && parentId ? Number(parentId) : null,
        });
      }
      onclose();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to save card";
    } finally {
      submitting = false;
    }
  }
</script>

<form class="card-form" onsubmit={submit}>
  {#if isEdit}
    <span class="ticket">{card!.ticket_number}</span>
  {/if}
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

  {#if !isEdit}
    <div class="row">
      <select bind:value={kind} aria-label="Kind">
        <option value="story">Story</option>
        <option value="epic">Epic</option>
      </select>
      {#if kind === "story"}
        <select bind:value={parentId} aria-label="Parent epic">
          <option value="">— no epic</option>
          {#each parentOptions as epic (epic.id)}
            <option value={String(epic.id)}>{epic.ticket_number} · {epic.title}</option>
          {/each}
        </select>
      {/if}
    </div>
  {/if}

  {#if error}
    <p class="form-error" role="alert">{error}</p>
  {/if}

  <div class="row actions">
    <button type="submit" class="primary" disabled={!canSubmit}>
      {isEdit ? "Save" : "Create"}
    </button>
    <button type="button" onclick={onclose} disabled={submitting}>Cancel</button>
    {#if isEdit && onrequestdelete}
      <button type="button" class="danger" onclick={onrequestdelete} disabled={submitting}>
        Delete
      </button>
    {/if}
  </div>
</form>
