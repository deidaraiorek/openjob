from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin


class RoleProfile(TimestampMixin, Base):
    __tablename__ = "role_profiles"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_role_profiles_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    prompt: Mapped[str] = mapped_column()
    generated_titles: Mapped[list[str]] = mapped_column(JSON, default=list)
    generated_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)

    account = relationship("Account", back_populates="role_profile")
