<script lang="ts">
  import type { Card } from "../api";
  import { epicFor, removeCard } from "../board.svelte";
  import CardForm from "./CardForm.svelte";

  let { card }: { card: Card } = $props();

  // The epic this story belongs to (if any) — rendered as a tag on the face.
  const epic = $derived(epicFor(card.epic_id));

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
      {#if card.story_points != null}
        <span class="points">{card.story_points}</span>
      {/if}
    </div>
    {#if epic}
      <div class="card-meta">
        <span class="epic-tag" title="{epic.ticket_number} · {epic.name}">{epic.name}</span>
      </div>
    {/if}
    <p class="card-title">{card.title}</p>
    {#if card.assignee}
      <span class="assignee">{card.assignee}</span>
    {/if}
    <div class="card-actions">
      <button class="link" onclick={() => (mode = "edit")}>Edit</button>
      <button class="link danger" onclick={() => (mode = "confirmDelete")}>Delete</button>
    </div>
  </article>
{/if}
