"""seed demo cards on a fresh board

Revision ID: 0002_seed_demo_cards
Revises: 0001_initial
Create Date: 2026-07-07

Data migration (R0.4): inserts a few demo cards so a fresh database shows a
lively board. Guarded to run only when the table is empty, so it is a no-op on
databases that already have cards (e.g. production on redeploy).

Self-contained snapshot: this migration carries its own board-less INSERT rather
than importing ``app.seed``. At this point in history the ``card`` table has no
``board_id`` column (that arrives in 0005, which also backfills these rows into
the default board). Decoupling from the live ``app.seed`` module — which since
M3 V7 targets the current schema with ``board_id`` — keeps this migration valid
on a fresh database years later.
"""
from typing import Sequence, Union

from sqlalchemy import text

from alembic import op

revision: str = "0002_seed_demo_cards"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (title, description, column, position, story_points, assignee) — the demo board
# as it was at this revision (no board_id yet).
_DEMO_CARDS: list[dict] = [
    dict(zip(("title", "description", "column", "position", "story_points", "assignee"), row))
    for row in [
        ("Set up project repository", "Monorepo: backend + frontend.", "done", 0, 2, "Alex"),
        ("Design the card data model", None, "done", 1, 3, "Sam"),
        ("Build the REST API", "CRUD + move endpoints.", "in_progress", 0, 8, "Sam"),
        ("Wire up drag-and-drop", "svelte-dnd-action between columns.", "in_progress", 1, 5, "Jordan"),
        ("Add demo seed data", None, "todo", 0, 2, None),
        ("Write end-to-end tests", "Playwright smoke coverage.", "todo", 1, 3, "Alex"),
    ]
]

_INSERT = text(
    'INSERT INTO card (title, description, "column", position, story_points, assignee) '
    "VALUES (:title, :description, :column, :position, :story_points, :assignee)"
)


def upgrade() -> None:
    conn = op.get_bind()
    # Guard: only seed a fresh board (no-op if any card already exists).
    if conn.execute(text("SELECT COUNT(*) FROM card")).scalar_one():
        return
    for card in _DEMO_CARDS:
        conn.execute(_INSERT, card)


def downgrade() -> None:
    # Best-effort removal of the demo cards by their (distinctive) titles.
    titles = [card["title"] for card in _DEMO_CARDS]
    op.get_bind().execute(text("DELETE FROM card WHERE title = ANY(:titles)"), {"titles": titles})
