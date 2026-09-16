from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.db.session import get_db
from app.models.integration_setting import IntegrationProvider
from app.services.integration_settings_service import IntegrationSettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Pydantic schemas ───────────────────────────────────────────────────────

class OktaSaveRequest(BaseModel):
    domain: str
    api_token: str
    sync_interval_hours: int = 6


class AzureSaveRequest(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str
    sync_interval_hours: int = 6


class IntegrationResponse(BaseModel):
    provider: str
    is_enabled: bool
    # Okta
    okta_domain: Optional[str] = None
    okta_configured: bool = False
    # Azure
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_configured: bool = False
    # Common
    sync_interval_hours: int = 6
    last_tested_at: Optional[datetime] = None
    last_test_ok: Optional[bool] = None
    last_test_error: Optional[str] = None

    model_config = {"from_attributes": True}


class TestResult(BaseModel):
    ok: bool
    message: str


# ── Helpers ────────────────────────────────────────────────────────────────

def _to_response(setting) -> IntegrationResponse:
    return IntegrationResponse(
        provider=setting.provider.value,
        is_enabled=setting.is_enabled,
        okta_domain=setting.okta_domain,
        okta_configured=bool(setting.okta_api_token_encrypted),
        azure_tenant_id=setting.azure_tenant_id,
        azure_client_id=setting.azure_client_id,
        azure_configured=bool(setting.azure_client_secret_encrypted),
        sync_interval_hours=setting.sync_interval_hours,
        last_tested_at=setting.last_tested_at,
        last_test_ok=setting.last_test_ok,
        last_test_error=setting.last_test_error,
    )


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(db: AsyncSession = Depends(get_db)):
    """Return current configuration for all integrations (tokens are never returned)."""
    svc = IntegrationSettingsService(db)
    settings = await svc.get_all()
    return [_to_response(s) for s in settings]


# ── Okta ───────────────────────────────────────────────────────────────────

@router.get("/okta", response_model=IntegrationResponse)
async def get_okta(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.OKTA)
    if not setting:
        # Return an empty/unconfigured response rather than 404
        return IntegrationResponse(provider="okta", is_enabled=False)
    return _to_response(setting)


@router.post("/okta", response_model=IntegrationResponse)
async def save_okta(payload: OktaSaveRequest, db: AsyncSession = Depends(get_db)):
    """Save Okta credentials. The token is encrypted before storage."""
    svc = IntegrationSettingsService(db)
    setting = await svc.save_okta(
        domain=payload.domain,
        api_token=payload.api_token,
        sync_interval_hours=payload.sync_interval_hours,
    )
    await db.commit()
    return _to_response(setting)


@router.post("/okta/test", response_model=TestResult)
async def test_okta(db: AsyncSession = Depends(get_db)):
    """Test the saved Okta credentials with a live API call."""
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.OKTA)
    if not setting:
        raise HTTPException(status_code=400, detail="Okta not configured yet.")
    ok, message = await svc.test_okta(setting)
    await svc.record_test_result(setting, ok, None if ok else message)
    await db.commit()
    return TestResult(ok=ok, message=message)


@router.post("/okta/enable", response_model=IntegrationResponse)
async def enable_okta(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.set_enabled(IntegrationProvider.OKTA, True)
    if not setting:
        raise HTTPException(status_code=400, detail="Configure Okta first.")
    await db.commit()
    return _to_response(setting)


@router.post("/okta/disable", response_model=IntegrationResponse)
async def disable_okta(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.set_enabled(IntegrationProvider.OKTA, False)
    if not setting:
        raise HTTPException(status_code=400, detail="Okta not configured.")
    await db.commit()
    return _to_response(setting)


# ── Azure AD ───────────────────────────────────────────────────────────────

@router.get("/azure-ad", response_model=IntegrationResponse)
async def get_azure(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.AZURE_AD)
    if not setting:
        return IntegrationResponse(provider="azure_ad", is_enabled=False)
    return _to_response(setting)


@router.post("/azure-ad", response_model=IntegrationResponse)
async def save_azure(payload: AzureSaveRequest, db: AsyncSession = Depends(get_db)):
    """Save Azure AD credentials. The client secret is encrypted before storage."""
    svc = IntegrationSettingsService(db)
    setting = await svc.save_azure(
        tenant_id=payload.tenant_id,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        sync_interval_hours=payload.sync_interval_hours,
    )
    await db.commit()
    return _to_response(setting)


@router.post("/azure-ad/test", response_model=TestResult)
async def test_azure(db: AsyncSession = Depends(get_db)):
    """Test the saved Azure AD credentials with a live API call."""
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.AZURE_AD)
    if not setting:
        raise HTTPException(status_code=400, detail="Azure AD not configured yet.")
    ok, message = await svc.test_azure(setting)
    await svc.record_test_result(setting, ok, None if ok else message)
    await db.commit()
    return TestResult(ok=ok, message=message)


@router.post("/azure-ad/enable", response_model=IntegrationResponse)
async def enable_azure(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.set_enabled(IntegrationProvider.AZURE_AD, True)
    if not setting:
        raise HTTPException(status_code=400, detail="Configure Azure AD first.")
    await db.commit()
    return _to_response(setting)


@router.post("/azure-ad/disable", response_model=IntegrationResponse)
async def disable_azure(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.set_enabled(IntegrationProvider.AZURE_AD, False)
    if not setting:
        raise HTTPException(status_code=400, detail="Azure AD not configured.")
    await db.commit()
    return _to_response(setting)
