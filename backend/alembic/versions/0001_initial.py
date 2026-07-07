"""initial card table + ticket sequence

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-07

Creates the ticket-number sequence first, then the `card` table whose
`ticket_number` defaults to 'KAN-' || nextval(seq) — atomic, immutable, no reuse
(ADR 0006). `column` is a varchar guarded by a CHECK constraint (ADR 0008).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sequence must exist before the table default references it.
    op.execute("CREATE SEQUENCE card_ticket_seq START 1")

    op.create_table(
        "card",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "ticket_number",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'KAN-' || nextval('card_ticket_seq')"),
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("column", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("story_points", sa.Integer(), nullable=True),
        sa.Column("assignee", sa.String(length=255), nullable=True),
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
        sa.UniqueConstraint("ticket_number", name="uq_card_ticket_number"),
        sa.CheckConstraint(
            "\"column\" IN ('todo', 'in_progress', 'done')",
            name="ck_card_column",
        ),
    )
    # Tie the sequence's lifecycle to the table so DROP TABLE cleans it up.
    op.execute("ALTER SEQUENCE card_ticket_seq OWNED BY card.id")


def downgrade() -> None:
    op.drop_table("card")
    op.execute("DROP SEQUENCE IF EXISTS card_ticket_seq")
