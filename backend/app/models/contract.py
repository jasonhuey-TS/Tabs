import enum
import uuid
from datetime import datetime, date
from sqlalchemy import String, Enum, Integer, Boolean, Text, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class ContractStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING_RENEWAL = "pending_renewal"
    IN_NEGOTIATION = "in_negotiation"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)

    status: Mapped[ContractStatus] = mapped_column(Enum(ContractStatus), default=ContractStatus.ACTIVE, index=True)

    # Dates
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    signed_date: Mapped[date | None] = mapped_column(Date)

    # Auto-renewal
    auto_renews: Mapped[bool] = mapped_column(Boolean, default=False)
    cancellation_notice_days: Mapped[int | None] = mapped_column(Integer)  # days before end_date to cancel

    # Value
    total_value_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Ownership
    owner_email: Mapped[str | None] = mapped_column(String(255))  # person responsible for renewal
    vendor_contact: Mapped[str | None] = mapped_column(String(255))

    # File (stored in S3)
    file_key: Mapped[str | None] = mapped_column(String(512))  # S3 object key
    file_name: Mapped[str | None] = mapped_column(String(255))

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    app: Mapped["App"] = relationship("App", back_populates="contracts")
    renewal_alerts: Mapped[list["RenewalAlert"]] = relationship("RenewalAlert", back_populates="contract", cascade="all, delete-orphan")

    @property
    def days_until_expiry(self) -> int | None:
        if not self.end_date:
            return None
        from datetime import date as date_
        return (self.end_date - date_.today()).days

    @property
    def cancellation_deadline(self) -> date | None:
        if not self.end_date or not self.cancellation_notice_days:
            return None
        from datetime import timedelta
        return self.end_date - timedelta(days=self.cancellation_notice_days)
