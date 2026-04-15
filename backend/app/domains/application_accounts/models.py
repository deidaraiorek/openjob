from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ApplicationAccount(TimestampMixin, Base):
    __tablename__ = "application_accounts"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "platform_family",
            "tenant_host",
            name="uq_application_accounts_account_platform_tenant",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    platform_family: Mapped[str] = mapped_column(String(80))
    tenant_host: Mapped[str] = mapped_column(String(255), default="")
    login_identifier: Mapped[str] = mapped_column(String(255))
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    credential_status: Mapped[str] = mapped_column(String(32), default="ready")
    last_successful_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    account = relationship("Account", back_populates="application_accounts")
