<script lang="ts">
  import type { Card as CardType, Column } from "../api";
  import Card from "./Card.svelte";
  import CardForm from "./CardForm.svelte";

  let {
    column,
    label,
    cards,
  }: { column: Column; label: string; cards: CardType[] } = $props();

  let adding = $state(false);
</script>

<section class="column">
  <header class="column-head">
    <h2>{label}</h2>
    <span class="count">{cards.length}</span>
  </header>

  <div class="cards">
    {#each cards as card (card.id)}
      <Card {card} />
    {/each}

    {#if cards.length === 0}
      <p class="empty">No cards yet</p>
    {/if}
  </div>

  {#if adding}
    <CardForm {column} onclose={() => (adding = false)} />
  {:else}
    <button class="add" onclick={() => (adding = true)}>+ Add card</button>
  {/if}
</section>
