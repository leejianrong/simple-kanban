"""board auto-sync opt-in flags

Revision ID: 0011_board_autosync_flags
Revises: 0010_board_members
Create Date: 2026-07-13

KAN-43. Per-board opt-in for mapping GitHub webhook events onto card updates.
Two boolean flags on ``board``, both NOT NULL and defaulting to ``false`` so
existing boards stay opted-out until their owner turns auto-sync on:

- ``autosync_enabled`` — master switch. When false the webhook does NOTHING to
  this board's cards (attach PR link / post CI comment / advance on merge).
- ``autosync_advance_to_done`` — SEPARATE switch gating only the "move card to
  ``done`` on PR merge" action, keeping the human in the loop for 'done'.

Hand-written (autogenerate is noisy in this repo — it spuriously reports
migration-created indexes as removed and drops ``sa.Identity``).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0011_board_autosync_flags"
down_revision: Union[str, None] = "0010_board_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "board",
        sa.Column(
            "autosync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "board",
        sa.Column(
            "autosync_advance_to_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("board", "autosync_advance_to_done")
    op.drop_column("board", "autosync_enabled")
