"""seed demo cards on a fresh board

Revision ID: 0002_seed_demo_cards
Revises: 0001_initial
Create Date: 2026-07-07

Data migration (R0.4): inserts a few demo cards so a fresh database shows a
lively board. Guarded to run only when the table is empty, so it is a no-op on
databases that already have cards (e.g. production on redeploy).
"""
from typing import Sequence, Union

from sqlalchemy import text

from alembic import op
from app.seed import DEMO_CARDS, seed_demo_cards

revision: str = "0002_seed_demo_cards"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    seed_demo_cards(op.get_bind())


def downgrade() -> None:
    # Best-effort removal of the demo cards by their (distinctive) titles.
    titles = [card["title"] for card in DEMO_CARDS]
    op.get_bind().execute(text("DELETE FROM card WHERE title = ANY(:titles)"), {"titles": titles})
