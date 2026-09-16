import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"           # full access
    IT_MANAGER = "it_manager" # manage apps, licenses, contracts
    FINANCE = "finance"       # read spend, contracts; no edit
    VIEWER = "viewer"         # read-only


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255))  # null if SSO-only
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    department: Mapped[str | None] = mapped_column(String(255))

    # SSO identity linkage
    okta_user_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    azure_object_id: Mapped[str | None] = mapped_column(String(255), unique=True)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    app_users: Mapped[list["AppUser"]] = relationship("AppUser", back_populates="user")
