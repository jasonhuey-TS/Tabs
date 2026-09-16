import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class AppUserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"   # provisioned but not logging in
    DEPROVISIONED = "deprovisioned"


class AppUser(Base):
    """Tracks which platform users are provisioned to which SaaS apps."""
    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("app_id", "user_id", name="uq_app_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status: Mapped[AppUserStatus] = mapped_column(Enum(AppUserStatus), default=AppUserStatus.ACTIVE)
    role_in_app: Mapped[str | None] = mapped_column(String(100))  # "admin", "member", etc.

    # Usage tracking
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_count_30d: Mapped[int | None] = mapped_column()

    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deprovisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    app: Mapped["App"] = relationship("App", back_populates="app_users")
    user: Mapped["User"] = relationship("User", back_populates="app_users")
