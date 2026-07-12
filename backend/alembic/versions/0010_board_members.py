"""board membership (user <-> board + role)

Revision ID: 0010_board_members
Revises: 0009_card_comments
Create Date: 2026-07-13

KAN-12. A board can have members (users other than the owner) with a role. A
``board_member`` row is (``board_id``, ``user_id``, ``role``). Roles are
``viewer`` / ``editor`` / ``owner``, guarded by a CHECK constraint in the
``card.column`` varchar style (so a new role needs no ``ALTER TYPE`` migration).

Both FKs ``ON DELETE CASCADE`` — deleting a board or a user removes the membership
row (consistent with the app's hard-delete model). ``UNIQUE(board_id, user_id)``
keeps a user's membership of a board singular; ``board_id`` is indexed for the
read-side member listing.

This migration adds the table only — role-based read/write enforcement (KAN-13)
and list-visibility (KAN-15) are later slices.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID

from alembic import op

revision: str = "0010_board_members"
down_revision: Union[str, None] = "0009_card_comments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "board_member",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "board_id",
            sa.BigInteger(),
            sa.ForeignKey("board.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint(
            "role IN ('viewer', 'editor', 'owner')", name="ck_board_member_role"
        ),
        sa.UniqueConstraint("board_id", "user_id", name="uq_board_member"),
    )
    op.create_index("ix_board_member_board_id", "board_member", ["board_id"])


def downgrade() -> None:
    op.drop_index("ix_board_member_board_id", table_name="board_member")
    op.drop_table("board_member")
