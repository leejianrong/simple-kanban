"""Demo seed data for a fresh board (R0.4).

A handful of cards across the three columns so the very first load shows a lively
board instead of an empty one. Kept as plain data plus a guarded insert so both
the Alembic data migration and any future management command can reuse it. Uses
Core SQL against the ``card`` table (no ORM models), so it stays valid even if the
ORM layer later changes — important for a migration that must run years from now.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

# (title, description, column, position, story_points, assignee)
_FIELDS = ("title", "description", "column", "position", "story_points", "assignee")
_ROWS: list[tuple] = [
    ("Set up project repository", "Monorepo: backend + frontend.", "done", 0, 2, "Alex"),
    ("Design the card data model", None, "done", 1, 3, "Sam"),
    ("Build the REST API", "CRUD + move endpoints.", "in_progress", 0, 8, "Sam"),
    ("Wire up drag-and-drop", "svelte-dnd-action between columns.", "in_progress", 1, 5, "Jordan"),
    ("Add demo seed data", None, "todo", 0, 2, None),
    ("Write end-to-end tests", "Playwright smoke coverage.", "todo", 1, 3, "Alex"),
]

# List of demo cards as dicts; the source of truth for both insert and cleanup.
DEMO_CARDS: list[dict] = [dict(zip(_FIELDS, row)) for row in _ROWS]

_INSERT = text(
    'INSERT INTO card (title, description, "column", position, story_points, assignee) '
    "VALUES (:title, :description, :column, :position, :story_points, :assignee)"
)


def seed_demo_cards(connection: Connection) -> int:
    """Insert the demo cards, but only when the board is empty.

    Returns the number of cards inserted (0 if the board already has any card, so
    running this on an existing/production database is a safe no-op). ``id``,
    ``ticket_number``, and the timestamps are left to their DB defaults.
    """
    existing = connection.execute(text("SELECT COUNT(*) FROM card")).scalar_one()
    if existing:
        return 0
    for card in DEMO_CARDS:
        connection.execute(_INSERT, card)
    return len(DEMO_CARDS)
