"""saved_view: named, persisted card queries per board (M5 V14)

Revision ID: 0016_saved_views
Revises: 0015_card_needs_human
Create Date: 2026-07-17

KAN-247 (M5 V14, query depth + saved views). Additive & back-compat (R5.3): a new
``saved_view`` table only — no change to any existing table, so every board/card
keeps working untouched.

- ``saved_view`` — ``(id, board_id FK → board ON DELETE CASCADE, name, query JSON,
  created_at)``. ``query`` stores the structured filter+sort grammar
  (``schemas.CardQuery``) as JSON; replaying it as ``GET /cards`` query params
  reproduces the view's result set. Deleting a board cascades its saved views away.
- An index on ``board_id`` for the board-scoped list.

Reversible: ``downgrade`` drops the index + table.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0016_saved_views"
down_revision: Union[str, None] = "0015_card_needs_human"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_view",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "board_id",
            sa.BigInteger(),
            sa.ForeignKey("board.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("query", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_saved_view_board_id", "saved_view", ["board_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_view_board_id", table_name="saved_view")
    op.drop_table("saved_view")
