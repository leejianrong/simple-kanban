"""activity: structured from_column/to_column for move transitions

Revision ID: 0019_activity_transition_columns
Revises: 0018_activity_purged_action
Create Date: 2026-07-20

KAN-260 (M5 V17, harden metrics). Additive & back-compat (R5.3): add two nullable
``varchar`` columns to ``activity`` recording the structured column transition of a
``moved`` event, so the metrics layer (``app.metrics``) reads the transition from
these fields instead of parsing the human ``summary`` text.

- ``activity.from_column`` — the source column of a move (NULL for non-move rows and
  for rows written before this migration).
- ``activity.to_column`` — the destination column of a move (same NULL semantics).

Both are plain nullable ``varchar`` with **no CHECK** — a CHECK rejecting NULL would
break back-compat with historical rows (which are all NULL), and only the move
handlers write these, from the ``VALID_COLUMNS`` vocabulary. Mirrors the additive
column style of migration 0014.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0019_activity_transition_columns"
down_revision: Union[str, None] = "0018_activity_purged_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activity",
        sa.Column("from_column", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "activity",
        sa.Column("to_column", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("activity", "to_column")
    op.drop_column("activity", "from_column")
