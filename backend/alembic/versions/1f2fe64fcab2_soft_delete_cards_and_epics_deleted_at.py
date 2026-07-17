"""soft-delete cards and epics (deleted_at)

Revision ID: 1f2fe64fcab2
Revises: 0012_activity_log
Create Date: 2026-07-17 10:42:58.045697

KAN-19 (M4 "Trust & History", R5.2). Add a nullable ``deleted_at`` tombstone to
both ``card`` and ``epic``. DELETE becomes a soft delete (sets ``deleted_at =
now()``); default reads filter ``deleted_at IS NULL`` so a deleted row is invisible
to lists, get-by-id, the ordering helpers and autosync, yet survives for a future
restore (KAN-20). NULL = live; a timestamp = deleted.

Only the two column adds belong here — autogenerate also reports dropping several
pre-existing FK indexes (``ix_card_comment_card_id`` etc.), but those are unrelated
false positives (indexes created by earlier migrations that the ORM doesn't declare
``index=True`` for); they are intentionally left in place.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f2fe64fcab2"
down_revision: Union[str, None] = "0012_activity_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "epic", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("epic", "deleted_at")
    op.drop_column("card", "deleted_at")
