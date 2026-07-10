<script lang="ts">
  import { untrack } from "svelte";
  import { X } from "lucide-svelte";
  import type { Card, Column } from "../api";
  import {
    addBlocker,
    addCard,
    board,
    editCard,
    epicStore,
    removeBlocker,
  } from "../board.svelte";

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
  const { isEdit, iTitle, iDesc, iAssignee, iPts, iEpic } = untrack(() => ({
    isEdit: !!card,
    iTitle: card?.title ?? "",
    iDesc: card?.description ?? "",
    iAssignee: card?.assignee ?? "",
    iPts: card?.story_points != null ? String(card.story_points) : "",
    iEpic: card?.epic_id != null ? String(card.epic_id) : "",
  }));

  let title = $state(iTitle);
  let description = $state(iDesc);
  let assignee = $state(iAssignee);
  let storyPoints = $state<string>(iPts); // "" = unestimated
  let epicId = $state<string>(iEpic); // "" = no epic
  let submitting = $state(false);
  let error = $state<string | null>(null);

  // Epics this story can be linked to (create + edit).
  const epicOptions = $derived(epicStore.epics);

  // --- Blockers (KAN-30, edit mode only) ---------------------------------
  // Read straight off the (reactive) card prop, NOT a snapshot: add/remove are
  // their own server calls followed by refetch(), so `card.blocked_by` reflects
  // the latest edges without reopening the form. Candidates to add = same-board
  // cards, excluding this card and its existing blockers (the server also rejects
  // self / dup / cross-board / cycles with a 422, surfaced below).
  const blockers = $derived(
    isEdit ? card!.blocked_by.map((id) => board.cards.find((c) => c.id === id)) : [],
  );
  const blockerCandidates = $derived(
    isEdit
      ? board.cards.filter(
          (c) => c.id !== card!.id && !card!.blocked_by.includes(c.id),
        )
      : [],
  );
  let addBlockerId = $state<string>("");
  let depBusy = $state(false);
  let depError = $state<string | null>(null);

  async function onAddBlocker(blockerId: string) {
    if (!blockerId) return;
    depBusy = true;
    depError = null;
    try {
      await addBlocker(card!.id, Number(blockerId));
    } catch (e) {
      depError = e instanceof Error ? e.message : "Failed to add blocker";
    } finally {
      addBlockerId = ""; // reset the picker whether it succeeded or not
      depBusy = false;
    }
  }

  async function onRemoveBlocker(blockerId: number) {
    depBusy = true;
    depError = null;
    try {
      await removeBlocker(card!.id, blockerId);
    } catch (e) {
      depError = e instanceof Error ? e.message : "Failed to remove blocker";
    } finally {
      depBusy = false;
    }
  }

  const dirty = $derived(
    title.trim() !== iTitle ||
      description.trim() !== iDesc ||
      assignee.trim() !== iAssignee ||
      storyPoints !== iPts ||
      epicId !== iEpic,
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
      epic_id: epicId ? Number(epicId) : null,
    };
    try {
      if (isEdit) {
        await editCard(card!.id, fields);
      } else {
        await addCard({ ...fields, column: column! });
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

  <select bind:value={epicId} aria-label="Epic">
    <option value="">— no epic</option>
    {#each epicOptions as epic (epic.id)}
      <option value={String(epic.id)}>{epic.ticket_number} · {epic.name}</option>
    {/each}
  </select>

  {#if isEdit}
    <div class="blockers-edit">
      <span class="field-label">Blocked by</span>
      {#if blockers.length > 0}
        <ul class="blocker-list">
          {#each blockers as b}
            {#if b}
              <li class="blocker-item">
                <span class="blocker-ref" title={b.title}>
                  {b.ticket_number} · {b.title}
                </span>
                <button
                  type="button"
                  class="icon-btn danger"
                  title="Remove blocker"
                  aria-label="Remove blocker {b.ticket_number}"
                  disabled={depBusy}
                  onclick={() => onRemoveBlocker(b.id)}
                >
                  <X size={14} />
                </button>
              </li>
            {/if}
          {/each}
        </ul>
      {/if}
      <select
        bind:value={addBlockerId}
        aria-label="Add blocker"
        disabled={depBusy || blockerCandidates.length === 0}
        onchange={() => onAddBlocker(addBlockerId)}
      >
        <option value="">
          {blockerCandidates.length === 0 ? "— no cards to add" : "— add a blocker"}
        </option>
        {#each blockerCandidates as c (c.id)}
          <option value={String(c.id)}>{c.ticket_number} · {c.title}</option>
        {/each}
      </select>
      {#if depError}
        <p class="form-error" role="alert">{depError}</p>
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
