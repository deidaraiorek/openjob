"""initial control plane schema

Revision ID: 20260402_01
Revises:
Create Date: 2026-04-02 23:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260402_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_accounts_email", "accounts", ["email"], unique=True)

    op.create_table(
        "job_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("account_id", "source_key", name="uq_job_sources_account_key"),
    )
    op.create_index("ix_job_sources_account_id", "job_sources", ["account_id"], unique=False)

    op.create_table(
        "role_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("generated_titles", sa.JSON(), nullable=False),
        sa.Column("generated_keywords", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("account_id", name="uq_role_profiles_account"),
    )
    op.create_index("ix_role_profiles_account_id", "role_profiles", ["account_id"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("canonical_key", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("account_id", "canonical_key", name="uq_jobs_account_canonical"),
    )
    op.create_index("ix_jobs_account_id", "jobs", ["account_id"], unique=False)

    op.create_table(
        "question_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=255), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("field_type", sa.String(length=80), nullable=False),
        sa.Column("option_labels", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint(
            "account_id",
            "fingerprint",
            name="uq_question_templates_account_fingerprint",
        ),
    )
    op.create_index(
        "ix_question_templates_account_id",
        "question_templates",
        ["account_id"],
        unique=False,
    )

    op.create_table(
        "answer_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("question_template_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["question_template_id"], ["question_templates.id"]),
    )
    op.create_index("ix_answer_entries_account_id", "answer_entries", ["account_id"], unique=False)

    op.create_table(
        "apply_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("destination_url", sa.String(length=500), nullable=False),
        sa.Column("is_preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
    )
    op.create_index("ix_apply_targets_job_id", "apply_targets", ["job_id"], unique=False)

    op.create_table(
        "application_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("apply_target_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["apply_target_id"], ["apply_targets.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
    )
    op.create_index("ix_application_runs_account_id", "application_runs", ["account_id"], unique=False)
    op.create_index("ix_application_runs_job_id", "application_runs", ["job_id"], unique=False)

    op.create_table(
        "job_sightings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("external_job_id", sa.String(length=255), nullable=True),
        sa.Column("listing_url", sa.String(length=500), nullable=False),
        sa.Column("apply_url", sa.String(length=500), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["job_sources.id"]),
    )
    op.create_index("ix_job_sightings_job_id", "job_sightings", ["job_id"], unique=False)

    op.create_table(
        "question_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("application_run_id", sa.Integer(), nullable=True),
        sa.Column("question_template_id", sa.Integer(), nullable=True),
        sa.Column("linked_answer_entry_id", sa.Integer(), nullable=True),
        sa.Column("question_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("field_type", sa.String(length=80), nullable=False),
        sa.Column("option_labels", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["application_run_id"], ["application_runs.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["linked_answer_entry_id"], ["answer_entries.id"]),
        sa.ForeignKeyConstraint(["question_template_id"], ["question_templates.id"]),
    )
    op.create_index("ix_question_tasks_account_id", "question_tasks", ["account_id"], unique=False)
    op.create_index("ix_question_tasks_job_id", "question_tasks", ["job_id"], unique=False)

    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_run_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_run_id"], ["application_runs.id"]),
    )
    op.create_index(
        "ix_application_events_application_run_id",
        "application_events",
        ["application_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_application_events_application_run_id", table_name="application_events")
    op.drop_table("application_events")
    op.drop_index("ix_question_tasks_job_id", table_name="question_tasks")
    op.drop_index("ix_question_tasks_account_id", table_name="question_tasks")
    op.drop_table("question_tasks")
    op.drop_index("ix_job_sightings_job_id", table_name="job_sightings")
    op.drop_table("job_sightings")
    op.drop_index("ix_application_runs_job_id", table_name="application_runs")
    op.drop_index("ix_application_runs_account_id", table_name="application_runs")
    op.drop_table("application_runs")
    op.drop_index("ix_apply_targets_job_id", table_name="apply_targets")
    op.drop_table("apply_targets")
    op.drop_index("ix_answer_entries_account_id", table_name="answer_entries")
    op.drop_table("answer_entries")
    op.drop_index("ix_question_templates_account_id", table_name="question_templates")
    op.drop_table("question_templates")
    op.drop_index("ix_jobs_account_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_role_profiles_account_id", table_name="role_profiles")
    op.drop_table("role_profiles")
    op.drop_index("ix_job_sources_account_id", table_name="job_sources")
    op.drop_table("job_sources")
    op.drop_index("ix_accounts_email", table_name="accounts")
    op.drop_table("accounts")
