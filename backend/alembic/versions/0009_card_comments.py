"""card notes / comments (human/agent-authored)

Revision ID: 0009_card_comments
Revises: 0008_card_links
Create Date: 2026-07-10

KAN-33. A card can carry intentional, human/agent-authored notes — a decision, a
handoff, "why this is blocked" — via a ``card_comment`` row (``body`` + author +
``created_at``). This is **distinct from Epic 4's SYSTEM activity log** (KAN-17..20,
not yet built): those entries are machine-generated audit events, whereas these are
deliberate authored notes. No activity-log machinery lives here — just the table.

``card_id`` FK ``ON DELETE CASCADE`` so deleting a card removes its comments;
indexed for the read-side comment listing. ``author_id`` FK → ``"user".id`` is
nullable with ``ON DELETE SET NULL`` — deleting the author keeps the note (mirrors
``board.owner_id``). The non-empty ``body`` rule is router-enforced (schema
validation), not a table constraint.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID

from alembic import op

revision: str = "0009_card_comments"
down_revision: Union[str, None] = "0008_card_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "card_comment",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "card_id",
            sa.BigInteger(),
            sa.ForeignKey("card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            GUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_card_comment_card_id", "card_comment", ["card_id"])


def downgrade() -> None:
    op.drop_index("ix_card_comment_card_id", table_name="card_comment")
    op.drop_table("card_comment")
