"""card full-text search vector (M5 V15)

Revision ID: 0017_card_search_vector
Revises: 0016_saved_views
Create Date: 2026-07-17

KAN-248 (M5 V15, full-text search). Additive & back-compat (R5.3):

- ``card.search_vector`` — a Postgres ``tsvector`` maintained as a
  ``GENERATED ALWAYS AS (...) STORED`` column over ``title`` + ``description``. The
  title is weighted ``A`` and the description ``B`` (``setweight``) so ``ts_rank``
  scores a title hit above a description-only hit. The DB recomputes it on every
  INSERT/UPDATE, so it is always consistent with the row with no trigger and no
  app-side upkeep. The generating expression is IMMUTABLE (``setweight`` +
  ``to_tsvector(regconfig, text)`` with a constant config literal + ``||``), which
  Postgres requires for a stored generated column.
- A GIN index over it (``ix_card_search_vector``) so ``@@`` match + ``ts_rank``
  ranking stay fast.

Additive only — a new generated column + its index. Existing rows are backfilled by
Postgres at ``ADD COLUMN`` time; no existing table/row semantics change, so every
board/card keeps working untouched. Reversible: ``downgrade`` drops the index +
column.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017_card_search_vector"
down_revision: Union[str, None] = "0016_saved_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # GENERATED ALWAYS AS (...) STORED: Postgres maintains the tsvector itself on
    # every INSERT/UPDATE — no trigger. The expression must be IMMUTABLE, which the
    # two-arg to_tsvector(regconfig, text) with a constant 'english' literal is.
    op.execute(
        "ALTER TABLE card ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS ("
        "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
        ") STORED"
    )
    op.create_index(
        "ix_card_search_vector",
        "card",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_card_search_vector", table_name="card")
    op.drop_column("card", "search_vector")
