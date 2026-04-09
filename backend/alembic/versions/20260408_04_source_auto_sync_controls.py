"""source auto sync controls

Revision ID: 20260408_04
Revises: 20260403_02
Create Date: 2026-04-08 00:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alembic import op
import sqlalchemy as sa


revision = "20260408_04"
down_revision = "20260403_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_sources", sa.Column("auto_sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("job_sources", sa.Column("sync_interval_hours", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("job_sources", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_sources", sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_sources", sa.Column("sync_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_job_sources_next_sync_at", "job_sources", ["next_sync_at"], unique=False)
    op.create_index("ix_job_sources_sync_lease_expires_at", "job_sources", ["sync_lease_expires_at"], unique=False)

    bind = op.get_bind()
    now = datetime.now(UTC)
    next_sync_at = now + timedelta(hours=6)
    bind.execute(
        sa.text(
            """
            UPDATE job_sources
            SET auto_sync_enabled = 1,
                sync_interval_hours = 6,
                next_sync_at = :next_sync_at
            WHERE active = 1
            """
        ),
        {"next_sync_at": next_sync_at},
    )

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("job_sources", "auto_sync_enabled", server_default=None)
        op.alter_column("job_sources", "sync_interval_hours", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_job_sources_sync_lease_expires_at", table_name="job_sources")
    op.drop_index("ix_job_sources_next_sync_at", table_name="job_sources")
    op.drop_column("job_sources", "sync_lease_expires_at")
    op.drop_column("job_sources", "next_sync_at")
    op.drop_column("job_sources", "last_synced_at")
    op.drop_column("job_sources", "sync_interval_hours")
    op.drop_column("job_sources", "auto_sync_enabled")
