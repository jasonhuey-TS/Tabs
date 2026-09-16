import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class AlertStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class RenewalAlert(Base):
    __tablename__ = "renewal_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)

    days_before_expiry: Mapped[int] = mapped_column(Integer, nullable=False)  # 90, 60, 30, etc.
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.PENDING)

    # Delivery
    sent_to: Mapped[str | None] = mapped_column(String(255))   # email address
    sent_via: Mapped[str | None] = mapped_column(String(50))   # "email", "slack"
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Scheduling
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contract: Mapped["Contract"] = relationship("Contract", back_populates="renewal_alerts")
