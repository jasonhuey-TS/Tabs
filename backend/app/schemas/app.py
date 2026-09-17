import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from app.models.app import AppCategory, AppStatus


class AppBase(BaseModel):
    name: str
    vendor: str
    vendor_slug: str
    category: AppCategory = AppCategory.OTHER
    status: AppStatus = AppStatus.UNMANAGED
    description: str | None = None
    website: str | None = None
    logo_url: str | None = None
    owner_email: EmailStr | None = None
    department: str | None = None


class AppCreate(AppBase):
    pass


class AppUpdate(BaseModel):
    name: str | None = None
    category: AppCategory | None = None
    status: AppStatus | None = None
    description: str | None = None
    owner_email: EmailStr | None = None
    department: str | None = None


class AppResponse(AppBase):
    id: uuid.UUID
    is_shadow_it: bool
    first_seen_at: datetime
    last_seen_at: datetime
    discovered_via: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LicenseSummary(BaseModel):
    """Minimal license info included in app list."""
    id: uuid.UUID
    license_type: str
    seats_purchased: int | None
    seats_active: int | None
    total_annual_cost_cents: int | None
    utilization_pct: Decimal | None
    waste_cost_cents: int | None

    model_config = {"from_attributes": True}


class AppSummary(BaseModel):
    """App list view — includes source and license info."""
    id: uuid.UUID
    name: str
    vendor: str
    vendor_slug: str
    category: AppCategory
    status: AppStatus
    is_shadow_it: bool
    department: str | None
    last_seen_at: datetime
    discovered_via: str | None
    licenses: List[LicenseSummary] = []

    model_config = {"from_attributes": True}
