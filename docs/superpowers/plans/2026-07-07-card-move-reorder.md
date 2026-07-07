# Card Move & Reorder (R2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user drag a card between columns and reorder it within a column, persisted via a single `POST /api/cards/{id}/move` endpoint.

**Architecture:** One backend action re-sequences card `position` transactionally (insert-at-index in the target column, renumber the source column when it changes). The frontend uses `svelte-dnd-action` drag-and-drop; after every drop the client refetches `GET /api/cards` — server order is authoritative, no optimistic UI (Shape A, ADR 0007).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (sync) + psycopg v3 + Postgres + Alembic (backend); Svelte 5 (runes) + Vite + TypeScript + `svelte-dnd-action` (frontend); pytest + testcontainers (tests).

**Spec:** `docs/superpowers/specs/2026-07-07-card-move-reorder-design.md`

---

## File Structure

**Backend**
- Modify `backend/app/schemas.py` — add `CardMove` schema.
- Modify `backend/app/ordering.py` — add `renumber_column()` helper.
- Modify `backend/app/routers/cards.py` — add `POST /api/cards/{id}/move`.
- Create `backend/tests/test_move.py` — move/reorder API tests.

**Frontend**
- Modify `frontend/package.json` / `package-lock.json` — add `svelte-dnd-action` dependency.
- Modify `frontend/src/lib/api.ts` — add `CardMove` type + `moveCard()`.
- Modify `frontend/src/lib/board.svelte.ts` — add `moveCard()` state wrapper.
- Modify `frontend/src/lib/components/Column.svelte` — drag-and-drop wiring.
- Modify `frontend/src/app.css` — make empty columns droppable (`.cards` min-height).

**Prerequisites for running:** Docker daemon running (backend tests use testcontainers). Node 20+ and `uv` installed. Commands below note the directory to run them from.

---

## Task 1: Spike — validate `svelte-dnd-action` under Svelte 5 / Vite 8

De-risks the one external dependency before building on it. If it will not build/typecheck cleanly, we fall back to native HTML5 drag events (same endpoint, same UX) — decide here, not mid-feature.

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`
- Create (throwaway): `frontend/src/lib/components/DndSpike.svelte`

- [ ] **Step 1: Install the dependency**

Run (from `frontend/`): `npm install svelte-dnd-action`
Expected: installs and adds `svelte-dnd-action` to `dependencies` in `package.json`; lockfile updates; exit 0.

- [ ] **Step 2: Create a throwaway spike component**

Create `frontend/src/lib/components/DndSpike.svelte`:

```svelte
<script lang="ts">
  import { flip } from "svelte/animate";
  import { dndzone, TRIGGERS, type DndEvent } from "svelte-dnd-action";

  type Item = { id: number; name: string };
  let items = $state<Item[]>([
    { id: 1, name: "one" },
    { id: 2, name: "two" },
    { id: 3, name: "three" },
  ]);

  function consider(e: CustomEvent<DndEvent<Item>>) {
    items = e.detail.items;
  }
  function finalize(e: CustomEvent<DndEvent<Item>>) {
    items = e.detail.items;
    if (e.detail.info.trigger === TRIGGERS.DROPPED_INTO_ZONE) {
      // eslint-disable-next-line no-console
      console.log("dropped", e.detail.info.id, items.map((i) => i.id));
    }
  }
</script>

<div use:dndzone={{ items, flipDurationMs: 150 }} onconsider={consider} onfinalize={finalize}>
  {#each items as item (item.id)}
    <div animate:flip={{ duration: 150 }}>{item.name}</div>
  {/each}
</div>
```

- [ ] **Step 3: Typecheck and build with the spike present**

Run (from `frontend/`): `npm run check`
Expected: PASS — 0 errors. If it errors specifically on the `onconsider`/`onfinalize` attributes, record the exact message; the accepted fixes are (a) keep `onconsider`/`onfinalize` (Svelte 5 action-event syntax) and, if the action's types don't declare them, add a single `<!-- svelte-ignore ... -->` or cast the handlers, or (b) fall back to native HTML5 DnD (see Step 5).

Run (from `frontend/`): `npm run build`
Expected: PASS — Vite build completes, exit 0.

- [ ] **Step 4: Remove the throwaway spike file**

Run (from `frontend/`): `git rm -f src/lib/components/DndSpike.svelte` (or delete the file)
Expected: the spike component is gone; only the dependency change remains.

- [ ] **Step 5: Decision gate**

If Steps 1–3 passed: proceed with `svelte-dnd-action` as planned (Task 6).
If they failed and no clean fix exists: STOP and switch Task 6 to native HTML5 drag events (`draggable`, `dragstart`/`dragover`/`drop`) hitting the same `moveCard(id, { column, position })`. Note the decision in the commit message.

- [ ] **Step 6: Commit**

Run (from repo root):
```
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add svelte-dnd-action (spike validated on Svelte 5)"
```

---

## Task 2: Backend — `CardMove` schema, `renumber_column`, and move endpoint (append behavior)

TDD. Implements column change + append-to-end of the target column, source-column renumber, and validation/404. Honoring an explicit `position` (reorder/clamp) comes in Task 3.

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/ordering.py`
- Modify: `backend/app/routers/cards.py`
- Test: `backend/tests/test_move.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_move.py`:

```python
"""API tests for POST /api/cards/{id}/move (move & reorder, R2)."""
from __future__ import annotations


def _create(client, title, column="todo"):
    return client.post("/api/cards", json={"title": title, "column": column}).json()


def test_move_to_another_column_appends(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "in_progress"})
    assert r.status_code == 200
    body = r.json()
    assert body["column"] == "in_progress"
    assert body["position"] == 0


def test_move_between_columns_renumbers_source(client):
    a = _create(client, "A", "todo")  # pos 0
    b = _create(client, "B", "todo")  # pos 1
    c = _create(client, "C", "todo")  # pos 2
    client.post(f"/api/cards/{a['id']}/move", json={"column": "done"})
    cards = {x["id"]: x for x in client.get("/api/cards").json()}
    assert cards[a["id"]]["column"] == "done"
    assert cards[a["id"]]["position"] == 0
    assert cards[b["id"]]["position"] == 0  # source renumbered 0..n
    assert cards[c["id"]]["position"] == 1


def test_move_into_empty_column_lands_at_zero(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "done", "position": 0})
    assert r.status_code == 200
    assert r.json()["column"] == "done"
    assert r.json()["position"] == 0


def test_move_unknown_card_returns_404(client):
    r = client.post("/api/cards/999999/move", json={"column": "done"})
    assert r.status_code == 404


def test_move_rejects_unknown_column_422(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "backlog"})
    assert r.status_code == 422


def test_move_rejects_negative_position_422(client):
    a = _create(client, "A", "todo")
    r = client.post(f"/api/cards/{a['id']}/move", json={"column": "todo", "position": -1})
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `uv run pytest tests/test_move.py -v`
Expected: FAIL — the `/move` route does not exist yet (404/405 on the move calls; the 404-for-unknown-card test may coincidentally pass but the move-success tests fail).

- [ ] **Step 3: Add the `CardMove` schema**

In `backend/app/schemas.py`, after the `CardCreate` class, add:

```python
class CardMove(BaseModel):
    column: ColumnEnum
    position: int | None = Field(default=None, ge=0)
```

(`Field` and `ColumnEnum` are already imported/defined in this file.)

- [ ] **Step 4: Add the `renumber_column` helper**

In `backend/app/ordering.py`, after `next_position`, add:

```python
def renumber_column(db: Session, column: str) -> None:
    """Re-sequence a column's cards to contiguous positions 0..n."""
    cards = db.scalars(
        select(Card).where(Card.column == column).order_by(Card.position, Card.id)
    ).all()
    for index, card in enumerate(cards):
        card.position = index
```

(`select`, `Session`, and `Card` are already imported in this file.)

- [ ] **Step 5: Add the move endpoint (append behavior)**

In `backend/app/routers/cards.py`, update the imports:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from ..ordering import next_position, renumber_column
from ..schemas import CardCreate, CardMove, CardRead
```

Then append this endpoint to the file:

```python
@router.post("/{card_id}/move", response_model=CardRead)
def move_card(
    card_id: int, payload: CardMove, db: Session = Depends(get_db)
) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Card not found"
        )

    source_column = card.column
    target_column = payload.column.value

    # The target column's other cards, in order (the moved card excluded).
    siblings = list(
        db.scalars(
            select(Card)
            .where(Card.column == target_column, Card.id != card.id)
            .order_by(Card.position, Card.id)
        ).all()
    )

    # Task 2 always appends; Task 3 replaces this with a clamped insert-at-index.
    siblings.append(card)
    card.column = target_column
    for pos, sibling in enumerate(siblings):
        sibling.position = pos

    # Flush so the moved card's new column is visible to the source renumber query
    # (the session has autoflush disabled).
    db.flush()
    if source_column != target_column:
        renumber_column(db, source_column)

    db.commit()
    db.refresh(card)
    return card
```

- [ ] **Step 6: Run tests to verify they pass**

Run (from `backend/`): `uv run pytest tests/test_move.py -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 7: Run the full backend suite (no regressions)**

Run (from `backend/`): `uv run pytest -v`
Expected: PASS — the Task 2 tests plus the existing `test_cards.py` all green.

- [ ] **Step 8: Commit**

Run (from repo root):
```
git add backend/app/schemas.py backend/app/ordering.py backend/app/routers/cards.py backend/tests/test_move.py
git commit -m "feat(backend): move endpoint — column change + append + source renumber"
```

---

## Task 3: Backend — honor explicit `position` (reorder within column, clamping)

TDD. Adds insert-at-clamped-index so an explicit `position` reorders within a column and places precisely across columns.

**Files:**
- Modify: `backend/app/routers/cards.py`
- Test: `backend/tests/test_move.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_move.py`:

```python
def test_reorder_within_column(client):
    a = _create(client, "A", "todo")  # pos 0
    b = _create(client, "B", "todo")  # pos 1
    c = _create(client, "C", "todo")  # pos 2
    # Move C to the front of todo.
    client.post(f"/api/cards/{c['id']}/move", json={"column": "todo", "position": 0})
    cards = {x["id"]: x for x in client.get("/api/cards").json()}
    assert cards[c["id"]]["position"] == 0
    assert cards[a["id"]]["position"] == 1
    assert cards[b["id"]]["position"] == 2


def test_move_position_beyond_range_clamps_to_end(client):
    a = _create(client, "A", "todo")  # pos 0
    b = _create(client, "B", "todo")  # pos 1
    # Move A within todo to an out-of-range index -> clamps after B.
    client.post(f"/api/cards/{a['id']}/move", json={"column": "todo", "position": 99})
    cards = {x["id"]: x for x in client.get("/api/cards").json()}
    assert cards[b["id"]]["position"] == 0
    assert cards[a["id"]]["position"] == 1


def test_move_to_specific_index_in_other_column(client):
    x = _create(client, "X", "done")  # done pos 0
    y = _create(client, "Y", "done")  # done pos 1
    a = _create(client, "A", "todo")  # todo pos 0
    # Move A into done at index 1 (between X and Y).
    client.post(f"/api/cards/{a['id']}/move", json={"column": "done", "position": 1})
    cards = {c["id"]: c for c in client.get("/api/cards").json()}
    assert cards[x["id"]]["position"] == 0
    assert cards[a["id"]]["position"] == 1
    assert cards[y["id"]]["position"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `uv run pytest tests/test_move.py -v`
Expected: FAIL on the three new tests — the endpoint still appends (ignores `position`), so `test_reorder_within_column` and `test_move_to_specific_index_in_other_column` fail (C/A land at the end, not the requested index). `test_move_position_beyond_range_clamps_to_end` may pass since clamping-to-end equals append.

- [ ] **Step 3: Replace append with a clamped insert-at-index**

In `backend/app/routers/cards.py`, replace the single line:

```python
    # Task 2 always appends; Task 3 replaces this with a clamped insert-at-index.
    siblings.append(card)
```

with:

```python
    # Insert at the requested index (clamped); None => append to the end.
    index = payload.position if payload.position is not None else len(siblings)
    index = max(0, min(index, len(siblings)))
    siblings.insert(index, card)
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `uv run pytest tests/test_move.py -v`
Expected: PASS — all 9 tests green.

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run (from `backend/`): `uv run pytest -v`
Expected: PASS — all backend tests green.

- [ ] **Step 6: Commit**

Run (from repo root):
```
git add backend/app/routers/cards.py backend/tests/test_move.py
git commit -m "feat(backend): honor explicit position (reorder within column, clamped)"
```

---

## Task 4: Frontend — `moveCard` API client + board state wrapper

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/board.svelte.ts`

- [ ] **Step 1: Add the `CardMove` type and `moveCard` to the API client**

In `frontend/src/lib/api.ts`, after the `CardCreate` interface add:

```typescript
export interface CardMove {
  column: Column;
  position?: number | null;
}
```

Then after `createCard` add:

```typescript
export async function moveCard(id: number, payload: CardMove): Promise<Card> {
  const res = await fetch(`/api/cards/${id}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res.json();
}
```

- [ ] **Step 2: Add the `moveCard` state wrapper**

In `frontend/src/lib/board.svelte.ts`, update the import line to:

```typescript
import {
  createCard,
  listCards,
  moveCard as apiMoveCard,
  type Card,
  type CardCreate,
  type CardMove,
  type Column,
} from "./api";
```

Then after `addCard` add:

```typescript
export async function moveCard(id: number, payload: CardMove): Promise<void> {
  await apiMoveCard(id, payload);
  await refetch();
}
```

- [ ] **Step 3: Typecheck**

Run (from `frontend/`): `npm run check`
Expected: PASS — 0 errors.

- [ ] **Step 4: Commit**

Run (from repo root):
```
git add frontend/src/lib/api.ts frontend/src/lib/board.svelte.ts
git commit -m "feat(frontend): moveCard API client and board-state wrapper"
```

---

## Task 5: Frontend — drag-and-drop wiring in `Column.svelte`

Each column becomes a drop zone; cards are draggable. On drop into a zone the client computes the target index and calls `moveCard` → refetch. Uses `svelte-dnd-action`.

**Files:**
- Modify: `frontend/src/lib/components/Column.svelte`
- Modify: `frontend/src/app.css`

- [ ] **Step 1: Make empty columns easy drop targets**

In `frontend/src/app.css`, change the `.cards` rule's `min-height`:

```css
.cards {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 2.5rem;
}
```

- [ ] **Step 2: Rewrite `Column.svelte` with drag-and-drop**

Replace the entire contents of `frontend/src/lib/components/Column.svelte` with:

```svelte
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
```

- [ ] **Step 3: Typecheck and build**

Run (from `frontend/`): `npm run check`
Expected: PASS — 0 errors. (If the `onconsider`/`onfinalize` attributes error, apply the fix recorded in Task 1 Step 3.)

Run (from `frontend/`): `npm run build`
Expected: PASS — Vite build completes, exit 0.

- [ ] **Step 4: Commit**

Run (from repo root):
```
git add frontend/src/lib/components/Column.svelte frontend/src/app.css
git commit -m "feat(frontend): drag-and-drop move & reorder on the board"
```

---

## Task 6: End-to-end verification

Drive the real app to confirm the feature works, then confirm the whole test surface is green. No new files.

- [ ] **Step 1: Start Postgres (local dev DB)**

Run (from repo root): `docker compose up -d`
Expected: the `kanban` Postgres container is running on `localhost:5432` (matches the default `DATABASE_URL` in `backend/app/db.py`).

- [ ] **Step 2: Apply migrations**

Run (from `backend/`): `uv run alembic upgrade head`
Expected: migrations apply to `head` (schema + seed), exit 0.

- [ ] **Step 3: Start the backend**

Run (from `backend/`): `uv run uvicorn app.main:app --port 8000`
Expected: Uvicorn serves on `http://localhost:8000`; `GET http://localhost:8000/api/health` returns `{"status":"ok"}`.

- [ ] **Step 4: Start the frontend dev server**

Run (from `frontend/`): `npm run dev`
Expected: Vite serves on `http://localhost:5173` and proxies `/api` → `:8000`.

- [ ] **Step 5: Verify the feature in the browser (use the `/verify` flow)**

Confirm each, reloading the page (F5) after the drags to prove persistence (R2.3):
- Drag a card from Todo to In Progress — it moves columns; both column counts update.
- Drag a card within a column to reorder it — order changes.
- Drag a card into an empty column — it lands as the sole card.
- Reload: the new columns and order persist (came from `GET /api/cards`, not local state).
- Trigger an error path if easy (e.g. stop the backend, attempt a drag): the error banner appears and a retry refetches.

Expected: all behaviors as described; no console errors.

- [ ] **Step 6: Run the full backend test suite once more**

Run (from `backend/`): `uv run pytest -v`
Expected: PASS — all tests green.

- [ ] **Step 7: Final typecheck + build**

Run (from `frontend/`): `npm run check && npm run build`
Expected: both PASS.

---

## Self-Review notes (author)

- **Spec coverage:** R2.1 (Task 5 drop into another column), R2.2 (Task 3 reorder + Task 5 within-column drag), R2.3 (Task 6 reload check), R4.3 (Task 2/3 endpoint), R4.4 (Task 2 `422`/`404` tests), R8.1 (Tasks 2–3 pytest). Playwright smoke (R8.2) intentionally deferred per spec.
- **`renumber_column` naming** is consistent across ordering.py and its use in cards.py. `moveCard` (frontend) is aliased `apiMoveCard` in board state to avoid shadowing the exported wrapper.
- **`db.flush()`** before the source renumber is required because the session has `autoflush=False`; without it the renumber query would still see the moved card in its old column.
