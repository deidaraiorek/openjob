from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=True)

    sources = relationship("JobSource", back_populates="account")
    role_profile = relationship("RoleProfile", back_populates="account", uselist=False)
    jobs = relationship("Job", back_populates="account")
    question_templates = relationship("QuestionTemplate", back_populates="account")
    answer_entries = relationship("AnswerEntry", back_populates="account")
    question_tasks = relationship("QuestionTask", back_populates="account")
    application_runs = relationship("ApplicationRun", back_populates="account")
    job_relevance_tasks = relationship("JobRelevanceTask", back_populates="account")
