<script lang="ts">
  import type { Card, Column } from "../api";
  import CardForm from "./CardForm.svelte";

  let { column, label, cards }: { column: Column; label: string; cards: Card[] } =
    $props();

  let adding = $state(false);
</script>

<section class="column">
  <header class="column-head">
    <h2>{label}</h2>
    <span class="count">{cards.length}</span>
  </header>

  <div class="cards">
    {#each cards as card (card.id)}
      <article class="card">
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
