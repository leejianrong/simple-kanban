<script lang="ts">
  import { onMount } from "svelte";
  import Board from "./lib/components/Board.svelte";
  import Epics from "./lib/components/Epics.svelte";
  import { refetch, refetchEpics } from "./lib/board.svelte";

  // The board shows stories; epics are managed in a separate view (ADR 0009).
  // A simple top-bar toggle switches between them — no client-side router.
  let view = $state<"board" | "epics">("board");

  // Load both on mount: the board needs epics too (for each story's epic tag).
  onMount(() => {
    refetch();
    refetchEpics();
  });
</script>

<header class="topbar">
  <h1>Simple Kanban</h1>
  <nav class="topbar-nav">
    <button class:active={view === "board"} onclick={() => (view = "board")}>Board</button>
    <button class:active={view === "epics"} onclick={() => (view = "epics")}>Epics</button>
  </nav>
</header>

<main>
  {#if view === "board"}
    <Board />
  {:else}
    <Epics />
  {/if}
</main>
