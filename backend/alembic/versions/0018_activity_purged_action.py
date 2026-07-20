"""activity: allow the 'purged' action

Revision ID: 0018_activity_purged_action
Revises: 0017_card_search_vector
Create Date: 2026-07-20

KAN-239 (M4 "Trust & History"). Widen the ``ck_activity_action`` CHECK to admit a
new ``purged`` action, so **permanently destroying** a soft-deleted (KAN-19/KAN-20)
card/epic records a first-class audit event distinct from the ``deleted`` row the
soft-delete already logged (rather than recording nothing, or a confusing second
``deleted`` row). Only the CHECK vocabulary changes — no new columns. Mirrors the
drop + recreate established by migration 0013 (``restored``) and 0015
(``attention``/``resolved``).

Reversible: ``downgrade`` restores the prior 7-value CHECK. (If any ``purged`` rows
exist they must be removed/relabelled first, or the re-add of the narrower
constraint fails — expected for a down-migration that removes a value.)
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_activity_purged_action"
down_revision: Union[str, None] = "0017_card_search_vector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = (
    "action IN ('created', 'updated', 'deleted', 'moved', 'restored', "
    "'attention', 'resolved')"
)
_NEW = (
    "action IN ('created', 'updated', 'deleted', 'moved', 'restored', "
    "'attention', 'resolved', 'purged')"
)


def upgrade() -> None:
    op.drop_constraint("ck_activity_action", "activity", type_="check")
    op.create_check_constraint("ck_activity_action", "activity", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_activity_action", "activity", type_="check")
    op.create_check_constraint("ck_activity_action", "activity", _OLD)
