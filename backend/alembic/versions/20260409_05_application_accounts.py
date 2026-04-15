"""application accounts

Revision ID: 20260409_05
Revises: 20260408_03, 20260408_04
Create Date: 2026-04-09 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260409_05"
down_revision: Union[str, Sequence[str], None] = ("20260408_03", "20260408_04")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("platform_family", sa.String(length=80), nullable=False),
        sa.Column("tenant_host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("login_identifier", sa.String(length=255), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("credential_status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint(
            "account_id",
            "platform_family",
            "tenant_host",
            name="uq_application_accounts_account_platform_tenant",
        ),
    )
    op.create_index("ix_application_accounts_account_id", "application_accounts", ["account_id"], unique=False)

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("application_accounts", "tenant_host", server_default=None)
        op.alter_column("application_accounts", "credential_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_application_accounts_account_id", table_name="application_accounts")
    op.drop_table("application_accounts")
