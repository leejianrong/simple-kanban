<script lang="ts">
  // Board switcher in the top bar (M3 V7): select the active board, and
  // create / rename / delete boards. Selecting a board reloads the board view
  // for it (board.svelte.ts owns the state + server calls).
  import {
    addBoard,
    boardStore,
    editBoard,
    removeBoard,
    setActiveBoard,
    activeBoard,
  } from "../board.svelte";

  type Mode = "idle" | "creating" | "renaming" | "confirmDelete";
  let mode = $state<Mode>("idle");
  let name = $state("");
  let busy = $state(false);

  function onSelect(e: Event) {
    const id = Number((e.currentTarget as HTMLSelectElement).value);
    if (id && id !== boardStore.activeBoardId) setActiveBoard(id);
  }

  function startCreate() {
    name = "";
    mode = "creating";
  }
  function startRename() {
    name = activeBoard()?.name ?? "";
    mode = "renaming";
  }
  function cancel() {
    mode = "idle";
    name = "";
  }

  async function submit() {
    const trimmed = name.trim();
    if (busy) return;
    if (mode === "creating") {
      if (!trimmed) return;
      busy = true;
      try {
        await addBoard(trimmed);
        cancel();
      } finally {
        busy = false;
      }
    } else if (mode === "renaming") {
      const b = activeBoard();
      if (!b || !trimmed) return;
      busy = true;
      try {
        await editBoard(b.id, trimmed);
        cancel();
      } finally {
        busy = false;
      }
    }
  }

  async function confirmDelete() {
    const b = activeBoard();
    if (!b || busy) return;
    busy = true;
    try {
      await removeBoard(b.id);
      mode = "idle";
    } finally {
      busy = false;
    }
  }
</script>

<div class="board-switcher">
  {#if mode === "creating" || mode === "renaming"}
    <form
      onsubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <input
        placeholder={mode === "creating" ? "Board name (required)" : "Rename board"}
        bind:value={name}
        aria-label="Board name"
      />
      <button type="submit" class="primary" disabled={!name.trim() || busy}>
        {mode === "creating" ? "Create" : "Save"}
      </button>
      <button type="button" class="link" onclick={cancel}>Cancel</button>
    </form>
  {:else if mode === "confirmDelete"}
    <span class="confirm-msg">Delete “{activeBoard()?.name}” and all its cards?</span>
    <button class="danger" onclick={confirmDelete} disabled={busy}>Delete</button>
    <button class="link" onclick={() => (mode = "idle")}>Cancel</button>
  {:else}
    <select aria-label="Board" value={boardStore.activeBoardId} onchange={onSelect}>
      {#each boardStore.boards as b (b.id)}
        <option value={b.id}>{b.name}</option>
      {/each}
    </select>
    <button class="link" onclick={startCreate}>+ New board</button>
    {#if activeBoard()}
      <button class="link" onclick={startRename}>Rename</button>
      <button class="link danger" onclick={() => (mode = "confirmDelete")}>Delete</button>
    {/if}
  {/if}
</div>
