import enum
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Enum, Integer, Numeric, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class LicenseType(str, enum.Enum):
    PER_SEAT = "per_seat"
    ENTERPRISE = "enterprise"        # flat fee
    CONSUMPTION = "consumption"      # usage-based
    FREE = "free"
    FREEMIUM = "freemium"


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)

    license_type: Mapped[LicenseType] = mapped_column(Enum(LicenseType), default=LicenseType.PER_SEAT)

    # Seat counts
    seats_purchased: Mapped[int | None] = mapped_column(Integer)
    seats_assigned: Mapped[int | None] = mapped_column(Integer)  # provisioned in IdP
    seats_active: Mapped[int | None] = mapped_column(Integer)    # logged in within 30d

    # Cost (stored in cents to avoid float issues)
    cost_per_seat_cents: Mapped[int | None] = mapped_column(Integer)  # per seat per month
    total_annual_cost_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Billing
    billing_cycle: Mapped[str | None] = mapped_column(String(20))  # "monthly", "annual"
    next_billing_date: Mapped[date | None] = mapped_column(Date)

    # Utilization snapshot (updated by sync jobs)
    utilization_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # active/purchased * 100
    waste_seats: Mapped[int | None] = mapped_column(Integer)  # purchased - active
    waste_cost_cents: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(String(1000))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    app: Mapped["App"] = relationship("App", back_populates="licenses")

    def recalculate_utilization(self) -> None:
        """Recompute derived fields after seat counts are updated."""
        if self.seats_purchased and self.seats_active is not None:
            self.utilization_pct = Decimal(self.seats_active) / Decimal(self.seats_purchased) * 100
            self.waste_seats = max(0, self.seats_purchased - self.seats_active)
            if self.cost_per_seat_cents and self.waste_seats:
                self.waste_cost_cents = self.waste_seats * self.cost_per_seat_cents * 12
