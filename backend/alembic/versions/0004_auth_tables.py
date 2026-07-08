"""auth tables: user, oauth_account, access_token

Revision ID: 0004_auth_tables
Revises: 0003_epic_story_model
Create Date: 2026-07-08

Milestone 3 V6 (ADR 0011). Creates the fastapi-users auth tables on the one
shared Base (spike-validated). These are written only through the async engine:
- `user`          — the human identity (UUID id, GitHub-verified email).
- `oauth_account` — a linked provider identity (GitHub now), FK → user, cascade.
- `access_token`  — a revocable cookie-session record for the DatabaseStrategy;
                    logout deletes the row. (Not the agent PATs, which arrive V9.)

The GUID / TIMESTAMPAware column types come from fastapi-users' generics so the
column definitions match what the ORM models expect.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID, TIMESTAMPAware

from alembic import op

revision: str = "0004_auth_tables"
down_revision: Union[str, None] = "0003_epic_story_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    op.create_table(
        "oauth_account",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("oauth_name", sa.String(length=100), nullable=False),
        sa.Column("access_token", sa.String(length=1024), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("refresh_token", sa.String(length=1024), nullable=True),
        sa.Column("account_id", sa.String(length=320), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_oauth_account_account_id"), "oauth_account", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_oauth_account_oauth_name"), "oauth_account", ["oauth_name"], unique=False
    )

    op.create_table(
        "access_token",
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column("created_at", TIMESTAMPAware(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="cascade"),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index(
        op.f("ix_access_token_created_at"), "access_token", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_access_token_created_at"), table_name="access_token")
    op.drop_table("access_token")
    op.drop_index(op.f("ix_oauth_account_oauth_name"), table_name="oauth_account")
    op.drop_index(op.f("ix_oauth_account_account_id"), table_name="oauth_account")
    op.drop_table("oauth_account")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
