"""boards: board table + card/epic board_id (backfilled into a default board)

Revision ID: 0005_boards
Revises: 0004_auth_tables
Create Date: 2026-07-08

Milestone 3 V7 (ADR 0012). Promotes the board to a first-class entity:
- a new `board` table (name + nullable `owner_id` → user, ON DELETE SET NULL).
- `card.board_id` / `epic.board_id`: NOT NULL FKs → board, ON DELETE CASCADE
  (deleting a board removes its cards + epics).

Migration (A8 / R6.1): create a single **default board** (unclaimed — owner_id
NULL, per the M3 V7 decision) and attach every existing card + epic to it, so no
data is lost. The columns are added nullable, backfilled, then set NOT NULL.
Ticket sequences are untouched — `KAN-`/`EPIC-` stay global across boards (D4).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID

from alembic import op

revision: str = "0005_boards"
down_revision: Union[str, None] = "0004_auth_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "board",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "owner_id",
            GUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # The default board that all pre-board cards/epics attach to. Unclaimed
    # (owner_id NULL) — V8 decides how it gets claimed.
    op.execute("INSERT INTO board (name) VALUES ('Default Board')")

    # Add board_id nullable, backfill to the default board, then enforce NOT NULL.
    op.add_column("card", sa.Column("board_id", sa.BigInteger(), nullable=True))
    op.add_column("epic", sa.Column("board_id", sa.BigInteger(), nullable=True))
    op.execute("UPDATE card SET board_id = (SELECT id FROM board ORDER BY id LIMIT 1)")
    op.execute("UPDATE epic SET board_id = (SELECT id FROM board ORDER BY id LIMIT 1)")
    op.alter_column("card", "board_id", nullable=False)
    op.alter_column("epic", "board_id", nullable=False)

    op.create_foreign_key(
        "fk_card_board_id", "card", "board", ["board_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_epic_board_id", "epic", "board", ["board_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("fk_epic_board_id", "epic", type_="foreignkey")
    op.drop_constraint("fk_card_board_id", "card", type_="foreignkey")
    op.drop_column("epic", "board_id")
    op.drop_column("card", "board_id")
    op.drop_table("board")
