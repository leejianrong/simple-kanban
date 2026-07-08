"""epic/story model: card.kind + card.parent_id

Revision ID: 0003_epic_story_model
Revises: 0002_seed_demo_cards
Create Date: 2026-07-08

Milestone 2 V1 (P1). Adds:
- `kind` varchar guarded by a CHECK constraint (`epic`|`story`, default `story`),
  mirroring the `column` pattern so a new kind needs no ALTER TYPE later (ADR 0008).
  The server_default backfills every existing row to `story`.
- `parent_id` nullable self-FK → card.id (a story's parent epic). ON DELETE SET NULL
  so deleting an epic detaches its stories, consistent with the hard-delete model.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_epic_story_model"
down_revision: Union[str, None] = "0002_seed_demo_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'story'"),
        ),
    )
    op.add_column(
        "card",
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
    )
    op.create_check_constraint(
        "ck_card_kind", "card", "kind IN ('epic', 'story')"
    )
    op.create_foreign_key(
        "fk_card_parent_id",
        "card",
        "card",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_card_parent_id", "card", type_="foreignkey")
    op.drop_constraint("ck_card_kind", "card", type_="check")
    op.drop_column("card", "parent_id")
    op.drop_column("card", "kind")
