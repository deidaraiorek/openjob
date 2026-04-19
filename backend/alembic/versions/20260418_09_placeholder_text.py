"""add placeholder_text to question_templates and question_tasks

Revision ID: 20260418_09
Revises: 20260416_08
Create Date: 2026-04-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260418_09"
down_revision: Union[str, Sequence[str], None] = "20260416_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("question_templates", sa.Column("placeholder_text", sa.Text(), nullable=True))
    op.add_column("question_tasks", sa.Column("placeholder_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("question_templates", "placeholder_text")
    op.drop_column("question_tasks", "placeholder_text")
