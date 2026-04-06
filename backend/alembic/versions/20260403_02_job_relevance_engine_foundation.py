"""job relevance engine foundation

Revision ID: 20260403_02
Revises: 20260402_01
Create Date: 2026-04-03 13:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260403_02"
down_revision: Union[str, Sequence[str], None] = "20260402_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "relevance_decision",
            sa.String(length=32),
            nullable=False,
            server_default="match",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "relevance_source",
            sa.String(length=32),
            nullable=False,
            server_default="system_migration",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("relevance_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("relevance_summary", sa.Text(), nullable=True),
    )

    op.execute(
        """
        UPDATE jobs
        SET
            relevance_decision = CASE
                WHEN status = 'filtered_out' THEN 'reject'
                ELSE 'match'
            END,
            relevance_source = CASE
                WHEN status = 'filtered_out' THEN 'system_migration'
                ELSE 'system_migration'
            END,
            relevance_summary = CASE
                WHEN status = 'filtered_out' THEN 'Migrated from legacy filtered_out job visibility.'
                ELSE 'Migrated from legacy visible job lifecycle state.'
            END
        """
    )

    op.create_table(
        "job_relevance_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("matched_signals", sa.JSON(), nullable=False),
        sa.Column("concerns", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("profile_snapshot_hash", sa.String(length=120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
    )
    op.create_index(
        "ix_job_relevance_evaluations_account_id",
        "job_relevance_evaluations",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_relevance_evaluations_job_id",
        "job_relevance_evaluations",
        ["job_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO job_relevance_evaluations (
            account_id,
            job_id,
            decision,
            source,
            score,
            summary,
            matched_signals,
            concerns,
            model_name,
            profile_snapshot_hash,
            payload,
            created_at,
            updated_at
        )
        SELECT
            account_id,
            id,
            relevance_decision,
            relevance_source,
            relevance_score,
            relevance_summary,
            '[]',
            '[]',
            NULL,
            NULL,
            '{}',
            created_at,
            updated_at
        FROM jobs
        """
    )


def downgrade() -> None:
    op.drop_index("ix_job_relevance_evaluations_job_id", table_name="job_relevance_evaluations")
    op.drop_index("ix_job_relevance_evaluations_account_id", table_name="job_relevance_evaluations")
    op.drop_table("job_relevance_evaluations")
    op.drop_column("jobs", "relevance_summary")
    op.drop_column("jobs", "relevance_score")
    op.drop_column("jobs", "relevance_source")
    op.drop_column("jobs", "relevance_decision")
