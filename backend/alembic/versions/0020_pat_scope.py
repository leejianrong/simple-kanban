"""personal_access_token: scope (observer vs operator)

Revision ID: 0020_pat_scope
Revises: 0019_activity_transition_columns
Create Date: 2026-07-20

KAN-251 (M5 V18, scoped tokens). Additive & back-compat (R5.3): add a ``scope``
column to ``personal_access_token`` recording whether a PAT is an **observer**
(``read`` — GET only) or an **operator** (``write`` — full board access, the
historical behaviour).

- ``scope`` — a plain ``varchar`` guarded by a ``CHECK (scope IN ('read','write'))``
  (the project's varchar+CHECK convention over a native PG enum, so a future scope
  value needs no ``ALTER TYPE``). ``server_default 'write'`` so **every existing
  PAT stays a writer** — no behaviour change for tokens minted before this slice.

Mirrors the additive column style of migration 0014.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0020_pat_scope"
down_revision: Union[str, None] = "0019_activity_transition_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personal_access_token",
        sa.Column(
            "scope",
            sa.String(length=16),
            nullable=False,
            server_default="write",
        ),
    )
    op.create_check_constraint(
        "ck_personal_access_token_scope",
        "personal_access_token",
        "scope IN ('read', 'write')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_personal_access_token_scope",
        "personal_access_token",
        type_="check",
    )
    op.drop_column("personal_access_token", "scope")
