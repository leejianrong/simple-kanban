"""activity: allow the 'restored' action

Revision ID: 0013_activity_restored_action
Revises: 1f2fe64fcab2
Create Date: 2026-07-17 12:00:00.000000

KAN-20 (M4 "Trust & History"). Widen the ``ck_activity_action`` CHECK to admit a
new ``restored`` action, so bringing a soft-deleted (KAN-19) card/epic back to life
records a first-class audit event distinct from ``deleted`` (rather than being
logged as an ``updated``). Only the CHECK vocabulary changes — no new columns.

Reversible: ``downgrade`` restores the original 4-value CHECK. (If any ``restored``
rows exist they must be removed/relabelled first, or the re-add of the narrower
constraint fails — expected for a down-migration that removes a value.)
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_activity_restored_action"
down_revision: Union[str, None] = "1f2fe64fcab2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "action IN ('created', 'updated', 'deleted', 'moved')"
_NEW = "action IN ('created', 'updated', 'deleted', 'moved', 'restored')"


def upgrade() -> None:
    op.drop_constraint("ck_activity_action", "activity", type_="check")
    op.create_check_constraint("ck_activity_action", "activity", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_activity_action", "activity", type_="check")
    op.create_check_constraint("ck_activity_action", "activity", _OLD)
