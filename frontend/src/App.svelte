<script lang="ts">
  import { onMount } from "svelte";
  import Board from "./lib/components/Board.svelte";
  import { refetch } from "./lib/board.svelte";

  onMount(refetch);
</script>

<header class="topbar">
  <h1>Simple Kanban</h1>
</header>

<main>
  <Board />
</main>
