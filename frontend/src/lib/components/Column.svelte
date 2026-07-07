<script lang="ts">
  import { flip } from "svelte/animate";
  import { dndzone, TRIGGERS, type DndEvent } from "svelte-dnd-action";
  import type { Card, Column } from "../api";
  import { moveCard } from "../board.svelte";
  import CardForm from "./CardForm.svelte";

  let { column, label, cards }: { column: Column; label: string; cards: Card[] } =
    $props();

  let adding = $state(false);

  // svelte-dnd-action owns a mutable copy of the list. Re-sync from the
  // server-authoritative `cards` prop whenever it changes (e.g. after refetch).
  let items = $state<Card[]>([]);
  $effect(() => {
    items = cards;
  });

  function handleConsider(e: CustomEvent<DndEvent<Card>>) {
    items = e.detail.items;
  }

  function handleFinalize(e: CustomEvent<DndEvent<Card>>) {
    items = e.detail.items;
    // Only the zone the card was dropped INTO issues the move; the source
    // zone's removal is handled server-side by renumber.
    if (e.detail.info.trigger === TRIGGERS.DROPPED_INTO_ZONE) {
      const id = Number(e.detail.info.id);
      const position = items.findIndex((c) => c.id === id);
      if (position >= 0) moveCard(id, { column, position });
    }
  }
</script>

<section class="column">
  <header class="column-head">
    <h2>{label}</h2>
    <span class="count">{items.length}</span>
  </header>

  <div
    class="cards"
    use:dndzone={{ items, flipDurationMs: 150, dropTargetStyle: { outline: "2px dashed #4c9aff" } }}
    onconsider={handleConsider}
    onfinalize={handleFinalize}
  >
    {#each items as card (card.id)}
      <article class="card" animate:flip={{ duration: 150 }}>
        <div class="card-top">
          <span class="ticket">{card.ticket_number}</span>
          {#if card.story_points != null}
            <span class="points">{card.story_points}</span>
          {/if}
        </div>
        <p class="card-title">{card.title}</p>
        {#if card.assignee}
          <span class="assignee">{card.assignee}</span>
        {/if}
      </article>
    {/each}
  </div>

  {#if items.length === 0}
    <p class="empty">No cards yet</p>
  {/if}

  {#if adding}
    <CardForm {column} onclose={() => (adding = false)} />
  {:else}
    <button class="add" onclick={() => (adding = true)}>+ Add card</button>
  {/if}
</section>
