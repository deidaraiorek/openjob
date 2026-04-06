from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, utcnow


class ApplicationRun(TimestampMixin, Base):
    __tablename__ = "application_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    apply_target_id: Mapped[int | None] = mapped_column(
        ForeignKey("apply_targets.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="queued")
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    account = relationship("Account", back_populates="application_runs")
    job = relationship("Job", back_populates="application_runs")
    apply_target = relationship("ApplyTarget")
    events = relationship(
        "ApplicationEvent",
        back_populates="application_run",
        cascade="all, delete-orphan",
    )
    question_tasks = relationship("QuestionTask", back_populates="application_run")


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_run_id: Mapped[int] = mapped_column(
        ForeignKey("application_runs.id"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    application_run = relationship("ApplicationRun", back_populates="events")
