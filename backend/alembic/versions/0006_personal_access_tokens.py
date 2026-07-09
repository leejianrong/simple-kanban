"""agent personal access tokens

Revision ID: 0006_personal_access_tokens
Revises: 0005_boards
Create Date: 2026-07-09

Milestone 3 V9 (ADR 0014). Self-serve agent **personal access tokens**: a
per-user, revocable, hashed bearer that authenticates as its owning user and
inherits that user's board access (ADR 0013's one authorization layer). Supersedes
V4's shared ``API_TOKENS`` env list (ADR 0010) as the agent auth mechanism.

Only the token's **hash** is stored (R7.1); ``token_hash`` is unique + indexed for
an O(1) auth lookup, ``user_id`` indexed for the "my tokens" list.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID

from alembic import op

revision: str = "0006_personal_access_tokens"
down_revision: Union[str, None] = "0005_boards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personal_access_token",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_personal_access_token_user_id", "personal_access_token", ["user_id"]
    )
    op.create_index(
        "ix_personal_access_token_token_hash",
        "personal_access_token",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_personal_access_token_token_hash", table_name="personal_access_token")
    op.drop_index("ix_personal_access_token_user_id", table_name="personal_access_token")
    op.drop_table("personal_access_token")
