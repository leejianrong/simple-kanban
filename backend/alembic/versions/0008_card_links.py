"""card work-links (PR / branch / CI)

Revision ID: 0008_card_links
Revises: 0007_card_dependencies
Create Date: 2026-07-10

KAN-32. A card can point at its real work state — its PR URL, branch, or CI run —
via a ``card_link`` row (``label`` + ``url``). ``card_id`` FK ``ON DELETE CASCADE``
so deleting a card removes its links; indexed for the read-side link lookups. The
non-empty ``label``/``url`` rule is router-enforced (schema validation), not a table
constraint.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008_card_links"
down_revision: Union[str, None] = "0007_card_dependencies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "card_link",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.BigInteger(),
            sa.ForeignKey("card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_card_link_card_id", "card_link", ["card_id"])


def downgrade() -> None:
    op.drop_index("ix_card_link_card_id", table_name="card_link")
    op.drop_table("card_link")
