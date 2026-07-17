"""card fields: priority, due_date, labels (M5 V11)

Revision ID: 0014_card_fields
Revises: 0013_activity_restored_action
Create Date: 2026-07-17

KAN-244 (M5 V11, the foundation of Milestone 5). Additive & back-compat (R5.3):

- ``card.priority`` — a ``varchar`` guarded by a CHECK (``none/low/medium/high/
  urgent``), the ``card.column`` pattern (ADR 0008); NOT NULL with a ``'none'``
  server default so every existing row stays valid.
- ``card.due_date`` — a nullable ``timestamptz`` (no default; NULL = no due date).
- ``label`` — a board-scoped, colored tag (``board_id`` FK ``ON DELETE CASCADE``,
  ``name``, ``color``), indexed for the board-scoped list.
- ``card_label`` — the M:N join (``card_id``/``label_id`` FKs, both ``ON DELETE
  CASCADE``, composite PK ``(card_id, label_id)``).

Both new tables and columns only add, so existing boards/cards keep working.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014_card_fields"
down_revision: Union[str, None] = "0013_activity_restored_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- card.priority (varchar + CHECK, default 'none') --------------------
    op.add_column(
        "card",
        sa.Column(
            "priority",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )
    op.create_check_constraint(
        "ck_card_priority",
        "card",
        "priority IN ('none', 'low', 'medium', 'high', 'urgent')",
    )

    # --- card.due_date (nullable timestamptz) -------------------------------
    op.add_column(
        "card",
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
    )

    # --- label (board-scoped, colored) --------------------------------------
    op.create_table(
        "label",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "board_id",
            sa.BigInteger(),
            sa.ForeignKey("board.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_label_board_id", "label", ["board_id"])

    # --- card_label (M:N join) ----------------------------------------------
    op.create_table(
        "card_label",
        sa.Column(
            "card_id",
            sa.BigInteger(),
            sa.ForeignKey("card.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "label_id",
            sa.BigInteger(),
            sa.ForeignKey("label.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("card_label")
    op.drop_index("ix_label_board_id", table_name="label")
    op.drop_table("label")
    op.drop_column("card", "due_date")
    op.drop_constraint("ck_card_priority", "card", type_="check")
    op.drop_column("card", "priority")
