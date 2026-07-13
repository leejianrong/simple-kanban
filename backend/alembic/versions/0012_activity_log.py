"""activity log (board-domain audit trail)

Revision ID: 0012_activity_log
Revises: 0011_board_autosync_flags
Create Date: 2026-07-13

KAN-17 (M4 "Trust & History", seeds R5.1). An append-only ``activity`` row per
successful board-domain mutation — create / update / delete / move of a card,
epic or board. This slice is the model + write path only; the read API + feed UI
are KAN-18.

- ``board_id`` FK → ``board`` (``ON DELETE CASCADE``): an activity belongs to a
  board and its whole audit trail is hard-deleted with the board. ``board_id`` is
  indexed for the KAN-18 per-board feed query.
- ``actor_user_id`` FK → ``user`` (``ON DELETE SET NULL``, nullable): the acting
  principal, kept nullable so deleting the user leaves the history unattributed
  (mirrors ``board.owner_id`` / ``card_comment.author_id``). ``actor_label`` is a
  denormalised human handle so the feed reads without a user join.
- ``entity_id`` is a plain integer, **not** an FK — the referenced entity may
  already be deleted (that's a ``deleted`` event), so the audit row must outlive it.
- ``entity_type`` / ``action`` are varchars guarded by CHECK constraints (the
  ``card.column`` pattern) so a new value needs no ``ALTER TYPE`` migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID

from alembic import op

revision: str = "0012_activity_log"
down_revision: Union[str, None] = "0011_board_autosync_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "board_id",
            sa.BigInteger(),
            sa.ForeignKey("board.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            GUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_label", sa.String(length=255), nullable=True),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "entity_type IN ('card', 'epic', 'board')",
            name="ck_activity_entity_type",
        ),
        sa.CheckConstraint(
            "action IN ('created', 'updated', 'deleted', 'moved')",
            name="ck_activity_action",
        ),
    )
    op.create_index("ix_activity_board_id", "activity", ["board_id"])


def downgrade() -> None:
    op.drop_index("ix_activity_board_id", table_name="activity")
    op.drop_table("activity")
