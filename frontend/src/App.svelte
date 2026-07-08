<script lang="ts">
  import { onMount } from "svelte";
  import Board from "./lib/components/Board.svelte";
  import Epics from "./lib/components/Epics.svelte";
  import Landing from "./lib/components/Landing.svelte";
  import BoardSwitcher from "./lib/components/BoardSwitcher.svelte";
  import { refetch, refetchBoards, refetchEpics } from "./lib/board.svelte";
  import { getCurrentUser, logout, type CurrentUser } from "./lib/api";

  // The board shows stories; epics are managed in a separate view (ADR 0009).
  // A simple top-bar toggle switches between them — no client-side router.
  let view = $state<"board" | "epics">("board");

  // Auth gating (M3 V6, A9): undefined = check in flight; null = logged out (show
  // the landing); a user = logged in (show the board). No client-side router — a
  // conditional render, matching the Board|Epics toggle style.
  let user = $state<CurrentUser | null | undefined>(undefined);

  onMount(async () => {
    try {
      user = await getCurrentUser();
    } catch {
      // Treat an unreachable/erroring auth check as logged-out (show the landing)
      // rather than getting stuck on a blank screen.
      user = null;
    }
    // Load boards first (picks the active board), then that board's cards + epics.
    if (user) {
      await refetchBoards();
      refetch();
      refetchEpics();
    }
  });

  async function handleLogout() {
    await logout();
    user = null;
  }
</script>

{#if user === undefined}
  <!-- Auth check in flight: render nothing so the landing doesn't flash. -->
{:else if user === null}
  <Landing />
{:else}
  <header class="topbar">
    <h1>Simple Kanban</h1>
    <nav class="topbar-nav">
      <button class:active={view === "board"} onclick={() => (view = "board")}>Board</button>
      <button class:active={view === "epics"} onclick={() => (view = "epics")}>Epics</button>
    </nav>
    <BoardSwitcher />
    <div class="topbar-user">
      <span class="user-email" title={user.email}>{user.email}</span>
      <button class="link" onclick={handleLogout}>Log out</button>
    </div>
  </header>

  <main>
    {#if view === "board"}
      <Board />
    {:else}
      <Epics />
    {/if}
  </main>
{/if}
