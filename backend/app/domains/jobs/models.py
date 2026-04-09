from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, utcnow


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("account_id", "canonical_key", name="uq_jobs_account_canonical"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    canonical_key: Mapped[str] = mapped_column(String(255))
    company_name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="discovered")
    relevance_decision: Mapped[str] = mapped_column(String(32), default="match")
    relevance_source: Mapped[str] = mapped_column(String(32), default="system_migration")
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    account = relationship("Account", back_populates="jobs")
    sightings = relationship(
        "JobSighting",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    apply_targets = relationship(
        "ApplyTarget",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    question_tasks = relationship(
        "QuestionTask",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    application_runs = relationship(
        "ApplicationRun",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    relevance_evaluations = relationship(
        "JobRelevanceEvaluation",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobRelevanceEvaluation.id.desc()",
    )
    relevance_tasks = relationship(
        "JobRelevanceTask",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobRelevanceTask.id.asc()",
    )


class JobSighting(Base):
    __tablename__ = "job_sightings"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("job_sources.id"), nullable=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_url: Mapped[str] = mapped_column(String(500), index=True, default="")
    listing_url: Mapped[str] = mapped_column(String(500))
    apply_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)

    job = relationship("Job", back_populates="sightings")
    source = relationship("JobSource", back_populates="sightings")


class ApplyTarget(TimestampMixin, Base):
    __tablename__ = "apply_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    destination_url: Mapped[str] = mapped_column(String(500))
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    job = relationship("Job", back_populates="apply_targets")


class JobRelevanceEvaluation(TimestampMixin, Base):
    __tablename__ = "job_relevance_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_signals: Mapped[list[str]] = mapped_column(JSON, default=list)
    concerns: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    profile_snapshot_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    account = relationship("Account")
    job = relationship("Job", back_populates="relevance_evaluations")


class JobRelevanceTask(TimestampMixin, Base):
    __tablename__ = "job_relevance_tasks"
    __table_args__ = (
        UniqueConstraint("job_id", "phase", name="uq_job_relevance_tasks_job_phase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    phase: Mapped[str] = mapped_column(String(32))
    available_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    last_failure_cause: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    account = relationship("Account")
    job = relationship("Job", back_populates="relevance_tasks")
