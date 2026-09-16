import uuid
from datetime import datetime, date
from pydantic import BaseModel, EmailStr
from app.models.contract import ContractStatus


class ContractBase(BaseModel):
    status: ContractStatus = ContractStatus.ACTIVE
    start_date: date | None = None
    end_date: date | None = None
    signed_date: date | None = None
    auto_renews: bool = False
    cancellation_notice_days: int | None = None
    total_value_cents: int | None = None
    currency: str = "USD"
    owner_email: EmailStr | None = None
    vendor_contact: str | None = None
    notes: str | None = None


class ContractCreate(ContractBase):
    app_id: uuid.UUID


class ContractUpdate(BaseModel):
    status: ContractStatus | None = None
    end_date: date | None = None
    auto_renews: bool | None = None
    cancellation_notice_days: int | None = None
    total_value_cents: int | None = None
    owner_email: EmailStr | None = None
    notes: str | None = None


class ContractResponse(ContractBase):
    id: uuid.UUID
    app_id: uuid.UUID
    file_key: str | None
    file_name: str | None
    days_until_expiry: int | None
    cancellation_deadline: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
