"""add system_events table for backend observability

Revision ID: 20260416_08
Revises: 20260410_07
Create Date: 2026-04-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260416_08"
down_revision: Union[str, Sequence[str], None] = "20260410_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_system_events_account_id", "system_events", ["account_id"])
    op.create_index("ix_system_events_source", "system_events", ["source"])
    op.create_index("ix_system_events_created_at", "system_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_system_events_created_at", table_name="system_events")
    op.drop_index("ix_system_events_source", table_name="system_events")
    op.drop_index("ix_system_events_account_id", table_name="system_events")
    op.drop_table("system_events")
