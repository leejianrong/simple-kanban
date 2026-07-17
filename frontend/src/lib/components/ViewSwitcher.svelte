<script lang="ts">
  // Saved-view switcher + query bar + board/table toggle (M5 V14, KAN-247).
  // Sits above the board: pick a saved view (applies its filter+sort), tweak the
  // live filters (priority / assignee / needs-human / sort), save the current
  // query as a named view, and flip between the board and a sortable table over
  // the same (filtered) cards. board.svelte.ts owns the state + server calls;
  // every change refetch()es, so the UI only shows server-confirmed cards.
  import { Bookmark, Columns3, Save, Table, Trash2, X } from "lucide-svelte";
  import {
    viewStore,
    setActiveView,
    setQuery,
    saveCurrentView,
    removeView,
    setViewMode,
  } from "../board.svelte";
  import type { Priority } from "../api";

  const PRIORITIES: Priority[] = ["none", "low", "medium", "high", "urgent"];
  // Sort presets over the shared grammar; "" = the server default order.
  const SORTS: { value: string; label: string }[] = [
    { value: "", label: "Default order" },
    { value: "-priority", label: "Priority (high→low)" },
    { value: "due_date", label: "Due date (soonest)" },
    { value: "-updated_at", label: "Recently updated" },
  ];

  let saving = $state(false);
  let newName = $state("");
  let busy = $state(false);

  function onSelectView(e: Event) {
    const raw = (e.currentTarget as HTMLSelectElement).value;
    setActiveView(raw === "" ? null : Number(raw));
  }

  function onPriority(e: Event) {
    const v = (e.currentTarget as HTMLSelectElement).value;
    setQuery({ priority: (v || undefined) as Priority | undefined });
  }

  let assigneeInput = $state("");
  // Keep the input in step when a saved view is applied.
  $effect(() => {
    assigneeInput = viewStore.query.assignee ?? "";
  });
  function onAssignee() {
    setQuery({ assignee: assigneeInput.trim() || undefined });
  }

  function onNeedsHuman(e: Event) {
    const checked = (e.currentTarget as HTMLInputElement).checked;
    setQuery({ needs_human: checked ? true : undefined });
  }

  function onSort(e: Event) {
    const v = (e.currentTarget as HTMLSelectElement).value;
    setQuery({ sort: v || undefined });
  }

  async function save() {
    const name = newName.trim();
    if (!name || busy) return;
    busy = true;
    try {
      await saveCurrentView(name);
      newName = "";
      saving = false;
    } finally {
      busy = false;
    }
  }

  async function deleteActive() {
    if (viewStore.activeViewId == null || busy) return;
    busy = true;
    try {
      await removeView(viewStore.activeViewId);
    } finally {
      busy = false;
    }
  }
</script>

<div class="view-bar">
  <div class="view-group">
    <Bookmark size={15} class="view-icon" aria-hidden="true" />
    <select
      class="rail-select"
      aria-label="Saved view"
      value={viewStore.activeViewId == null ? "" : String(viewStore.activeViewId)}
      onchange={onSelectView}
    >
      <option value="">All cards</option>
      {#each viewStore.views as v (v.id)}
        <option value={String(v.id)}>{v.name}</option>
      {/each}
    </select>
    {#if viewStore.activeViewId != null}
      <button
        class="icon-btn"
        title="Delete this view"
        aria-label="Delete this view"
        onclick={deleteActive}
        disabled={busy}
      >
        <Trash2 size={15} />
      </button>
    {/if}
  </div>

  <div class="view-filters">
    <label class="filter">
      <span>Priority</span>
      <select
        class="rail-select"
        aria-label="Filter by priority"
        value={viewStore.query.priority ?? ""}
        onchange={onPriority}
      >
        <option value="">Any</option>
        {#each PRIORITIES as p (p)}
          <option value={p}>{p}</option>
        {/each}
      </select>
    </label>

    <label class="filter">
      <span>Assignee</span>
      <input
        class="filter-input"
        placeholder="anyone"
        aria-label="Filter by assignee"
        bind:value={assigneeInput}
        onchange={onAssignee}
      />
    </label>

    <label class="filter checkbox">
      <input
        type="checkbox"
        aria-label="Only cards needing a human"
        checked={viewStore.query.needs_human === true}
        onchange={onNeedsHuman}
      />
      <span>Needs human</span>
    </label>

    <label class="filter">
      <span>Sort</span>
      <select
        class="rail-select"
        aria-label="Sort cards"
        value={viewStore.query.sort ?? ""}
        onchange={onSort}
      >
        {#each SORTS as s (s.value)}
          <option value={s.value}>{s.label}</option>
        {/each}
      </select>
    </label>
  </div>

  <div class="view-actions">
    {#if saving}
      <form
        class="save-form"
        onsubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <input
          class="filter-input"
          placeholder="View name"
          aria-label="View name"
          bind:value={newName}
        />
        <button type="submit" class="primary" disabled={!newName.trim() || busy}>Save</button>
        <button type="button" class="icon-btn" aria-label="Cancel" onclick={() => (saving = false)}>
          <X size={15} />
        </button>
      </form>
    {:else}
      <button class="chip-btn" onclick={() => (saving = true)}>
        <Save size={14} /> Save view
      </button>
    {/if}

    <div class="mode-toggle" role="group" aria-label="View mode">
      <button
        class:active={viewStore.mode === "board"}
        title="Board view"
        aria-label="Board view"
        aria-pressed={viewStore.mode === "board"}
        onclick={() => setViewMode("board")}
      >
        <Columns3 size={15} />
      </button>
      <button
        class:active={viewStore.mode === "table"}
        title="Table view"
        aria-label="Table view"
        aria-pressed={viewStore.mode === "table"}
        onclick={() => setViewMode("table")}
      >
        <Table size={15} />
      </button>
    </div>
  </div>
</div>

<style>
  .view-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.75rem 1rem;
    padding: 0.6rem 0.85rem;
    margin-bottom: 1rem;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .view-group,
  .view-actions {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .view-filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem 0.9rem;
    flex: 1 1 auto;
  }
  :global(.view-icon) {
    color: var(--muted);
  }
  .filter {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.8rem;
    color: var(--muted);
  }
  .filter.checkbox {
    gap: 0.3rem;
    cursor: pointer;
  }
  .filter-input {
    padding: 0.3rem 0.5rem;
    font: inherit;
    font-size: 0.82rem;
    color: var(--text);
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    max-width: 9rem;
  }
  .filter-input:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
  .save-form {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .chip-btn,
  .mode-toggle button {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.6rem;
    font: inherit;
    font-size: 0.82rem;
    color: var(--text);
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
  }
  .chip-btn:hover,
  .mode-toggle button:hover {
    background: var(--hover);
  }
  .mode-toggle {
    display: inline-flex;
    gap: 0.25rem;
  }
  .mode-toggle button.active {
    color: var(--accent);
    background: var(--accent-soft);
    border-color: var(--accent);
  }
  button.primary {
    padding: 0.35rem 0.7rem;
    font: inherit;
    font-size: 0.82rem;
    color: #fff;
    background: var(--accent);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    cursor: pointer;
  }
  button.primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
