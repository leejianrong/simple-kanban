"""card: needs_human handoff flag + attention_note, and the attention/resolved
activity actions (M5 V13)

Revision ID: 0015_card_needs_human
Revises: 0014_card_fields
Create Date: 2026-07-17

KAN-246 (M5 V13, the human↔agent handoff primitive). Additive & back-compat (R5.3):

- ``card.needs_human`` — a ``bool`` NOT NULL with a ``false`` server default, so
  every existing row stays valid after the migration (an unflagged card).
- ``card.attention_note`` — a nullable ``text`` carrying the optional human-readable
  ask an agent leaves when it flags a card (NULL = no note).
- ``ck_activity_action`` — widened to admit ``attention`` + ``resolved`` (the two
  new handoff events), mirroring EPIC-4's ``restored`` widening (migration 0013):
  a drop + recreate of the CHECK, reversible.

Everything only adds, so existing boards/cards keep working.

Reversible: ``downgrade`` drops the two columns and restores the pre-V13 5-value
CHECK. (If any ``attention``/``resolved`` activity rows exist they must be removed
or relabelled first, or re-adding the narrower constraint fails — expected for a
down-migration that removes a value.)
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0015_card_needs_human"
down_revision: Union[str, None] = "0014_card_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTION_OLD = "action IN ('created', 'updated', 'deleted', 'moved', 'restored')"
_ACTION_NEW = (
    "action IN ('created', 'updated', 'deleted', 'moved', 'restored', "
    "'attention', 'resolved')"
)


def upgrade() -> None:
    # --- card.needs_human (bool, NOT NULL, default false) -------------------
    op.add_column(
        "card",
        sa.Column(
            "needs_human",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # --- card.attention_note (nullable text) --------------------------------
    op.add_column(
        "card",
        sa.Column("attention_note", sa.Text(), nullable=True),
    )
    # --- widen ck_activity_action (add attention + resolved) ----------------
    op.drop_constraint("ck_activity_action", "activity", type_="check")
    op.create_check_constraint("ck_activity_action", "activity", _ACTION_NEW)


def downgrade() -> None:
    op.drop_constraint("ck_activity_action", "activity", type_="check")
    op.create_check_constraint("ck_activity_action", "activity", _ACTION_OLD)
    op.drop_column("card", "attention_note")
    op.drop_column("card", "needs_human")
