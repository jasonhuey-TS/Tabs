import uuid
from datetime import datetime
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


class AppSummary(BaseModel):
    """Lightweight version for list views."""
    id: uuid.UUID
    name: str
    vendor: str
    vendor_slug: str
    category: AppCategory
    status: AppStatus
    is_shadow_it: bool
    department: str | None
    last_seen_at: datetime

    model_config = {"from_attributes": True}
