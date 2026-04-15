"""add question_aliases table for semantic deduplication

Revision ID: 20260410_07
Revises: 20260409_06
Create Date: 2026-04-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260410_07"
down_revision: Union[str, Sequence[str], None] = "20260409_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("canonical_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="suggested"),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("account_id", "source_fingerprint", name="uq_question_aliases_account_source"),
    )
    op.create_index("ix_question_aliases_account_id", "question_aliases", ["account_id"])
    op.create_index("ix_question_aliases_status", "question_aliases", ["status"])


def downgrade() -> None:
    op.drop_index("ix_question_aliases_status", table_name="question_aliases")
    op.drop_index("ix_question_aliases_account_id", table_name="question_aliases")
    op.drop_table("question_aliases")
