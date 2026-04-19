"""add required to question_tasks

Revision ID: 20260419_10
Revises: 20260418_09
Create Date: 2026-04-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260419_10"
down_revision: Union[str, Sequence[str], None] = "20260418_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("question_tasks", sa.Column("required", sa.Boolean(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("question_tasks", "required")
