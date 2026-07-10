<script lang="ts">
  import { onMount } from "svelte";
  import { LogOut } from "lucide-svelte";
  import Board from "./lib/components/Board.svelte";
  import Epics from "./lib/components/Epics.svelte";
  import Landing from "./lib/components/Landing.svelte";
  import BoardSwitcher from "./lib/components/BoardSwitcher.svelte";
  import Tokens from "./lib/components/Tokens.svelte";
  import { refetch, refetchBoards, refetchEpics } from "./lib/board.svelte";
  import { refetchTokens } from "./lib/tokens.svelte";
  import { setSessionUser } from "./lib/session.svelte";
  import { getCurrentUser, logout, type CurrentUser } from "./lib/api";

  // The board shows stories; epics + agent tokens are managed in their own views.
  // A simple top-bar toggle switches between them — no client-side router.
  let view = $state<"board" | "epics" | "tokens">("board");

  // Tokens are user-scoped (not board-scoped), so load them lazily the first time
  // the Tokens view is opened.
  function show(next: typeof view) {
    view = next;
    if (next === "tokens") refetchTokens();
  }

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
    // Expose the user id for delete-own affordances deep in the tree (comments).
    setSessionUser(user?.id ?? null);
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
    setSessionUser(null);
  }
</script>

{#if user === undefined}
  <!-- Auth check in flight: render nothing so the landing doesn't flash. -->
{:else if user === null}
  <Landing />
{:else}
  <header class="topbar">
    <div class="brand">
      <span class="brand-glyph" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
      <h1>Simple Kanban</h1>
    </div>
    <nav class="topbar-nav">
      <button class:active={view === "board"} onclick={() => show("board")}>Board</button>
      <button class:active={view === "epics"} onclick={() => show("epics")}>Epics</button>
      <button class:active={view === "tokens"} onclick={() => show("tokens")}>Tokens</button>
    </nav>
    <BoardSwitcher />
    <div class="topbar-user">
      <span class="user-avatar" title={user.email} aria-hidden="true">
        {user.email.charAt(0).toUpperCase()}
      </span>
      <span class="user-email" title={user.email}>{user.email}</span>
      <button class="icon-btn" title="Log out" aria-label="Log out" onclick={handleLogout}>
        <LogOut size={16} />
      </button>
    </div>
  </header>

  <main>
    {#if view === "board"}
      <Board />
    {:else if view === "epics"}
      <Epics />
    {:else}
      <Tokens />
    {/if}
  </main>
{/if}
