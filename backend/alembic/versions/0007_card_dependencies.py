"""card-to-card dependencies

Revision ID: 0007_card_dependencies
Revises: 0006_personal_access_tokens
Create Date: 2026-07-09

KAN-28. A directed blocker→blocked edge between two cards (the foundation for the
dependency line). ``blocker_id`` blocks ``blocked_id`` — i.e. the blocked card is
*blocked-by* the blocker. Both FKs ``ON DELETE CASCADE`` so deleting a card removes
any edge it participates in. ``UNIQUE(blocker_id, blocked_id)`` keeps an edge
singular; both columns are indexed for the read-side dependency lookups.

Same-board, no-self-link and cycle-prevention are router-enforced (they can't be a
table constraint), not part of the schema.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0007_card_dependencies"
down_revision: Union[str, None] = "0006_personal_access_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "card_dependency",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "blocker_id",
            sa.BigInteger(),
            sa.ForeignKey("card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "blocked_id",
            sa.BigInteger(),
            sa.ForeignKey("card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "blocker_id", "blocked_id", name="uq_card_dependency_edge"
        ),
    )
    op.create_index(
        "ix_card_dependency_blocker_id", "card_dependency", ["blocker_id"]
    )
    op.create_index(
        "ix_card_dependency_blocked_id", "card_dependency", ["blocked_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_card_dependency_blocked_id", table_name="card_dependency")
    op.drop_index("ix_card_dependency_blocker_id", table_name="card_dependency")
    op.drop_table("card_dependency")
