"""github link compatibility metadata

Revision ID: 20260409_06
Revises: 20260409_05
Create Date: 2026-04-09 00:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260409_06"
down_revision: Union[str, Sequence[str], None] = "20260409_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_sources",
        sa.Column(
            "last_sync_summary_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("job_sources", "last_sync_summary_json", server_default=None)


def downgrade() -> None:
    op.drop_column("job_sources", "last_sync_summary_json")
