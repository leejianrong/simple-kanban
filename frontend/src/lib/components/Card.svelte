<script lang="ts">
  import { Ban, Pencil, Trash2 } from "lucide-svelte";
  import type { Card } from "../api";
  import { cardById, epicFor, removeCard } from "../board.svelte";
  import CardForm from "./CardForm.svelte";

  let { card }: { card: Card } = $props();

  // The epic this story belongs to (if any) — rendered as a tag on the face.
  const epic = $derived(epicFor(card.epic_id));

  // Dependency references, resolved to cards for their ticket + title. A ref that
  // isn't on the loaded board falls back to a bare `#id` (shouldn't happen —
  // dependencies are same-board — but keeps the render total).
  function ref(id: number): { ticket: string; title: string } {
    const c = cardById(id);
    return c
      ? { ticket: c.ticket_number, title: c.title }
      : { ticket: `#${id}`, title: `card ${id}` };
  }
  const blockedBy = $derived(card.blocked_by.map(ref));
  const blocks = $derived(card.blocks.map(ref));

  // Assignee avatar: first initial of the name/handle.
  const initials = $derived(card.assignee?.trim().charAt(0).toUpperCase() ?? "");

  // view (P1 face) · edit (P3) · confirmDelete (P4)
  let mode = $state<"view" | "edit" | "confirmDelete">("view");
  let deleting = $state(false);
  let deleteError = $state<string | null>(null);

  async function confirmDelete() {
    deleting = true;
    deleteError = null;
    try {
      await removeCard(card.id);
      // On success the card is gone from board state and this component unmounts.
    } catch (e) {
      deleteError = e instanceof Error ? e.message : "Failed to delete card";
      deleting = false;
    }
  }
</script>

{#if mode === "edit"}
  <CardForm
    {card}
    onclose={() => (mode = "view")}
    onrequestdelete={() => (mode = "confirmDelete")}
  />
{:else if mode === "confirmDelete"}
  <div class="card confirm">
    <p class="confirm-msg">
      Delete <strong>{card.ticket_number}</strong> — “{card.title}”? This can't be
      undone.
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
  <article class="card">
    <div class="card-top">
      <span class="ticket">{card.ticket_number}</span>
      {#if card.blocked}
        <span class="blocked-badge" title="Blocked by an unfinished card">
          <Ban size={11} aria-hidden="true" />
          Blocked
        </span>
      {/if}
      {#if epic}
        <span class="epic-tag" title="{epic.ticket_number} · {epic.name}">{epic.name}</span>
      {/if}
      {#if card.story_points != null}
        <span class="points" title="Story points">{card.story_points}</span>
      {/if}
    </div>
    <p class="card-title">{card.title}</p>
    {#if blockedBy.length > 0 || blocks.length > 0}
      <div class="deps">
        {#if blockedBy.length > 0}
          <p class="dep-line">
            <span class="dep-label">Blocked by</span>
            {#each blockedBy as b (b.ticket)}
              <span class="dep-ref" title={b.title}>{b.ticket}</span>
            {/each}
          </p>
        {/if}
        {#if blocks.length > 0}
          <p class="dep-line">
            <span class="dep-label">Blocks</span>
            {#each blocks as b (b.ticket)}
              <span class="dep-ref" title={b.title}>{b.ticket}</span>
            {/each}
          </p>
        {/if}
      </div>
    {/if}
    <div class="card-foot">
      {#if card.assignee}
        <span class="who">
          <span class="avatar-sm" aria-hidden="true">{initials}</span>
          <span class="who-name">{card.assignee}</span>
        </span>
      {/if}
      <div class="card-actions">
        <button class="icon-btn" title="Edit" aria-label="Edit" onclick={() => (mode = "edit")}>
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
  </article>
{/if}
