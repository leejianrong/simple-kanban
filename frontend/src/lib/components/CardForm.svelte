<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { X } from "lucide-svelte";
  import { addComment, deleteComment, listComments, type Card, type Column, type Comment } from "../api";
  import {
    addBlocker,
    addCard,
    addCardLink,
    board,
    editCard,
    epicStore,
    removeBlocker,
    removeCardLink,
  } from "../board.svelte";
  import { session } from "../session.svelte";

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

  // --- Work-links (KAN-34, edit mode only) --------------------------------
  // Read straight off the (reactive) card prop: add/remove are their own server
  // calls followed by refetch(), so `card.links` reflects the latest links without
  // reopening the form (links are inlined on card reads).
  const links = $derived(isEdit ? card!.links : []);
  let linkLabel = $state("");
  let linkUrl = $state("");
  let linkBusy = $state(false);
  let linkError = $state<string | null>(null);

  const canAddLink = $derived(
    linkLabel.trim().length > 0 && linkUrl.trim().length > 0 && !linkBusy,
  );

  async function onAddLink() {
    if (!canAddLink) return;
    linkBusy = true;
    linkError = null;
    try {
      await addCardLink(card!.id, linkLabel.trim(), linkUrl.trim());
      linkLabel = "";
      linkUrl = "";
    } catch (e) {
      linkError = e instanceof Error ? e.message : "Failed to add link";
    } finally {
      linkBusy = false;
    }
  }

  async function onRemoveLink(linkId: number) {
    linkBusy = true;
    linkError = null;
    try {
      await removeCardLink(card!.id, linkId);
    } catch (e) {
      linkError = e instanceof Error ? e.message : "Failed to remove link";
    } finally {
      linkBusy = false;
    }
  }

  // --- Comments / notes (KAN-34, edit mode only) --------------------------
  // Comments aren't inlined on card reads, so they get their own on-demand fetch
  // (loaded once when the edit form opens) and stay server-authoritative: after a
  // post/delete we re-list the thread rather than mutating it locally.
  let comments = $state<Comment[]>([]);
  let commentsLoaded = $state(false);
  let newComment = $state("");
  let commentBusy = $state(false);
  let commentError = $state<string | null>(null);

  async function loadComments() {
    if (!isEdit) return;
    try {
      comments = await listComments(card!.id);
    } catch (e) {
      commentError = e instanceof Error ? e.message : "Failed to load comments";
    } finally {
      commentsLoaded = true;
    }
  }

  onMount(loadComments);

  const canPostComment = $derived(newComment.trim().length > 0 && !commentBusy);

  async function onPostComment() {
    if (!canPostComment) return;
    commentBusy = true;
    commentError = null;
    try {
      await addComment(card!.id, newComment.trim());
      newComment = "";
      await loadComments();
    } catch (e) {
      commentError = e instanceof Error ? e.message : "Failed to post comment";
    } finally {
      commentBusy = false;
    }
  }

  async function onDeleteComment(commentId: number) {
    commentBusy = true;
    commentError = null;
    try {
      await deleteComment(card!.id, commentId);
      await loadComments();
    } catch (e) {
      commentError = e instanceof Error ? e.message : "Failed to delete comment";
    } finally {
      commentBusy = false;
    }
  }

  // A comment is deletable only by its author (the server also enforces this, 403).
  function ownComment(c: Comment): boolean {
    return session.userId != null && c.author_id === session.userId;
  }

  function formatWhen(iso: string): string {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
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

    <div class="links-edit">
      <span class="field-label">Links</span>
      {#if links.length > 0}
        <ul class="link-list">
          {#each links as l (l.id)}
            <li class="link-item">
              <a
                class="link-ref"
                href={l.url}
                target="_blank"
                rel="noopener noreferrer"
                title={l.url}
              >
                {l.label}
              </a>
              <button
                type="button"
                class="icon-btn danger"
                title="Remove link"
                aria-label="Remove link {l.label}"
                disabled={linkBusy}
                onclick={() => onRemoveLink(l.id)}
              >
                <X size={14} />
              </button>
            </li>
          {/each}
        </ul>
      {/if}
      <div class="row link-add">
        <input
          type="text"
          class="link-label-input"
          placeholder="Label (e.g. PR)"
          bind:value={linkLabel}
          disabled={linkBusy}
        />
        <input
          type="url"
          placeholder="https://…"
          bind:value={linkUrl}
          disabled={linkBusy}
        />
        <button type="button" disabled={!canAddLink} onclick={onAddLink}>Add</button>
      </div>
      {#if linkError}
        <p class="form-error" role="alert">{linkError}</p>
      {/if}
    </div>

    <div class="comments-edit">
      <span class="field-label">Notes</span>
      {#if commentsLoaded && comments.length > 0}
        <ul class="comment-list">
          {#each comments as c (c.id)}
            <li class="comment-item">
              <div class="comment-body">{c.body}</div>
              <div class="comment-meta">
                <time datetime={c.created_at}>{formatWhen(c.created_at)}</time>
                {#if ownComment(c)}
                  <button
                    type="button"
                    class="icon-btn danger"
                    title="Delete note"
                    aria-label="Delete note"
                    disabled={commentBusy}
                    onclick={() => onDeleteComment(c.id)}
                  >
                    <X size={13} />
                  </button>
                {/if}
              </div>
            </li>
          {/each}
        </ul>
      {:else if commentsLoaded}
        <p class="comment-empty">No notes yet.</p>
      {/if}
      <div class="row comment-add">
        <input
          type="text"
          placeholder="Add a note…"
          bind:value={newComment}
          disabled={commentBusy}
        />
        <button type="button" disabled={!canPostComment} onclick={onPostComment}>Post</button>
      </div>
      {#if commentError}
        <p class="form-error" role="alert">{commentError}</p>
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
