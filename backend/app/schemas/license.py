import uuid
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, field_validator
from app.models.license import LicenseType


class LicenseBase(BaseModel):
    license_type: LicenseType = LicenseType.PER_SEAT
    seats_purchased: int | None = None
    cost_per_seat_cents: int | None = None
    total_annual_cost_cents: int | None = None
    currency: str = "USD"
    billing_cycle: str | None = None
    next_billing_date: date | None = None
    notes: str | None = None


class LicenseCreate(LicenseBase):
    app_id: uuid.UUID


class LicenseUpdate(BaseModel):
    license_type: LicenseType | None = None
    seats_purchased: int | None = None
    seats_assigned: int | None = None
    seats_active: int | None = None
    cost_per_seat_cents: int | None = None
    total_annual_cost_cents: int | None = None
    billing_cycle: str | None = None
    next_billing_date: date | None = None
    notes: str | None = None


class LicenseResponse(LicenseBase):
    id: uuid.UUID
    app_id: uuid.UUID
    seats_assigned: int | None
    seats_active: int | None
    utilization_pct: Decimal | None
    waste_seats: int | None
    waste_cost_cents: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
