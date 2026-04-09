from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin


class JobSource(TimestampMixin, Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("account_id", "source_key", name="uq_job_sources_account_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(255))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sync_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    account = relationship("Account", back_populates="sources")
    sightings = relationship("JobSighting", back_populates="source")
