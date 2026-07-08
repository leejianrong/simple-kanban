"""epic entity + card.epic_id

Revision ID: 0003_epic_story_model
Revises: 0002_seed_demo_cards
Create Date: 2026-07-08

Milestone 2 V1 (ADR 0009). Introduces the epic as a first-class entity, separate
from the board's cards:
- a new `epic` table with its own `EPIC-<n>` ticket sequence (independent of the
  card `KAN-<n>` sequence — KAN-1 and EPIC-1 can coexist). Epics carry only a
  name + optional description; no column/position/assignee/story_points.
- `card.epic_id`: a nullable FK → epic.id (a story's parent epic). ON DELETE SET
  NULL so deleting an epic detaches its stories, consistent with the hard-delete
  model.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_epic_story_model"
down_revision: Union[str, None] = "0002_seed_demo_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sequence must exist before the table default references it.
    op.execute("CREATE SEQUENCE epic_ticket_seq START 1")

    op.create_table(
        "epic",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "ticket_number",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'EPIC-' || nextval('epic_ticket_seq')"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("ticket_number", name="uq_epic_ticket_number"),
    )
    # Tie the sequence's lifecycle to the table so DROP TABLE cleans it up.
    op.execute("ALTER SEQUENCE epic_ticket_seq OWNED BY epic.id")

    op.add_column("card", sa.Column("epic_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_card_epic_id",
        "card",
        "epic",
        ["epic_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_card_epic_id", "card", type_="foreignkey")
    op.drop_column("card", "epic_id")
    op.drop_table("epic")
    op.execute("DROP SEQUENCE IF EXISTS epic_ticket_seq")
