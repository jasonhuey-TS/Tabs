import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, Boolean, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class AppCategory(str, enum.Enum):
    PRODUCTIVITY = "productivity"
    COMMUNICATION = "communication"
    SECURITY = "security"
    DEVTOOLS = "devtools"
    HR = "hr"
    FINANCE = "finance"
    CRM = "crm"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    INFRASTRUCTURE = "infrastructure"
    DESIGN = "design"
    OTHER = "other"


class AppStatus(str, enum.Enum):
    MANAGED = "managed"        # IT-approved, tracked
    UNMANAGED = "unmanaged"    # discovered but not yet reviewed (shadow IT)
    SANCTIONED = "sanctioned"  # approved for use
    BLOCKED = "blocked"        # explicitly not allowed
    UNDER_REVIEW = "under_review"


class App(Base):
    __tablename__ = "apps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    # Canonical vendor slug for dedup matching ("microsoft-365", "slack", etc.)
    vendor_slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[AppCategory] = mapped_column(Enum(AppCategory), default=AppCategory.OTHER)
    status: Mapped[AppStatus] = mapped_column(Enum(AppStatus), default=AppStatus.UNMANAGED, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(512))
    logo_url: Mapped[str | None] = mapped_column(String(512))
    is_shadow_it: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Ownership
    owner_email: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(255))

    # Discovery metadata
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    discovered_via: Mapped[str | None] = mapped_column(String(50))  # "okta", "azure_ad", "csv"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    licenses: Mapped[list["License"]] = relationship("License", back_populates="app", cascade="all, delete-orphan")
    contracts: Mapped[list["Contract"]] = relationship("Contract", back_populates="app", cascade="all, delete-orphan")
    app_users: Mapped[list["AppUser"]] = relationship("AppUser", back_populates="app", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<App {self.name} ({self.vendor_slug})>"
