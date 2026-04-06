from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin


class QuestionTemplate(TimestampMixin, Base):
    __tablename__ = "question_templates"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "fingerprint",
            name="uq_question_templates_account_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(255))
    prompt_text: Mapped[str] = mapped_column()
    field_type: Mapped[str] = mapped_column(String(80))
    option_labels: Mapped[list[str]] = mapped_column(JSON, default=list)

    account = relationship("Account", back_populates="question_templates")
    answer_entries = relationship("AnswerEntry", back_populates="question_template")
    question_tasks = relationship("QuestionTask", back_populates="question_template")


class AnswerEntry(TimestampMixin, Base):
    __tablename__ = "answer_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    question_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_templates.id"),
        nullable=True,
    )
    label: Mapped[str] = mapped_column(String(255), default="Default answer")
    answer_text: Mapped[str | None] = mapped_column(nullable=True)
    answer_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    account = relationship("Account", back_populates="answer_entries")
    question_template = relationship("QuestionTemplate", back_populates="answer_entries")
    resolved_tasks = relationship("QuestionTask", back_populates="linked_answer_entry")


class QuestionTask(TimestampMixin, Base):
    __tablename__ = "question_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    application_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("application_runs.id"),
        nullable=True,
    )
    question_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_templates.id"),
        nullable=True,
    )
    linked_answer_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("answer_entries.id"),
        nullable=True,
    )
    question_fingerprint: Mapped[str] = mapped_column(String(255))
    prompt_text: Mapped[str] = mapped_column()
    field_type: Mapped[str] = mapped_column(String(80))
    option_labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="new")
    notes: Mapped[str | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    account = relationship("Account", back_populates="question_tasks")
    job = relationship("Job", back_populates="question_tasks")
    question_template = relationship("QuestionTemplate", back_populates="question_tasks")
    linked_answer_entry = relationship("AnswerEntry", back_populates="resolved_tasks")
    application_run = relationship("ApplicationRun", back_populates="question_tasks")
