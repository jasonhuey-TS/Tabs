"""
Integration Library endpoints — configure and sync deeper app integrations
(Slack, Zoom) to get last active dates and license types per user.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.db.session import get_db
from app.models.integration_setting import IntegrationProvider
from app.services.integration_settings_service import IntegrationSettingsService
from app.core.encryption import encrypt, decrypt

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ── Schemas ───────────────────────────────────────────────────────────────

class SlackSaveRequest(BaseModel):
    bot_token: str
    workspace_id: Optional[str] = None


class ZoomSaveRequest(BaseModel):
    account_id: str
    client_id: str
    client_secret: str


class IntegrationStatus(BaseModel):
    provider: str
    is_configured: bool
    is_enabled: bool
    last_tested_at: Optional[str] = None
    last_test_ok: Optional[bool] = None
    last_test_error: Optional[str] = None
    meta: dict = {}


class EnrichResult(BaseModel):
    ok: bool
    message: str
    users_updated: Optional[int] = None


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[IntegrationStatus])
async def list_integrations(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    results = []

    # Slack
    slack = await svc.get(IntegrationProvider.SLACK)
    results.append(IntegrationStatus(
        provider="slack",
        is_configured=bool(slack and slack.slack_bot_token_encrypted),
        is_enabled=bool(slack and slack.is_enabled),
        last_tested_at=slack.last_tested_at.isoformat() if slack and slack.last_tested_at else None,
        last_test_ok=slack.last_test_ok if slack else None,
        last_test_error=slack.last_test_error if slack else None,
        meta={"workspace_id": slack.slack_workspace_id} if slack else {},
    ))

    # Zoom
    zoom = await svc.get(IntegrationProvider.ZOOM)
    results.append(IntegrationStatus(
        provider="zoom",
        is_configured=bool(zoom and zoom.zoom_client_secret_encrypted),
        is_enabled=bool(zoom and zoom.is_enabled),
        last_tested_at=zoom.last_tested_at.isoformat() if zoom and zoom.last_tested_at else None,
        last_test_ok=zoom.last_test_ok if zoom else None,
        last_test_error=zoom.last_test_error if zoom else None,
        meta={"account_id": zoom.zoom_account_id, "client_id": zoom.zoom_client_id} if zoom else {},
    ))

    return results


# ── Slack ──────────────────────────────────────────────────────────────────

@router.post("/slack")
async def save_slack(payload: SlackSaveRequest, db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.SLACK)
    if not setting:
        from app.models.integration_setting import IntegrationSetting
        setting = IntegrationSetting(provider=IntegrationProvider.SLACK)
        db.add(setting)
    setting.slack_bot_token_encrypted = encrypt(payload.bot_token.strip())
    if payload.workspace_id:
        setting.slack_workspace_id = payload.workspace_id
    await db.commit()
    return {"ok": True, "message": "Slack credentials saved."}


@router.post("/slack/test")
async def test_slack(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.SLACK)
    if not setting or not setting.slack_bot_token_encrypted:
        return {"ok": False, "message": "Slack not configured."}
    try:
        token = decrypt(setting.slack_bot_token_encrypted)
        from app.integrations.slack.client import SlackClient
        async with SlackClient(bot_token=token) as slack:
            auth = await slack.test_auth()
        msg = f"Connected to workspace: {auth.get('team', 'unknown')}"
        setting.last_test_ok = True
        setting.last_test_error = None
    except Exception as exc:
        msg = str(exc)
        setting.last_test_ok = False
        setting.last_test_error = msg[:500]
    from datetime import datetime, timezone
    setting.last_tested_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": setting.last_test_ok, "message": msg}


@router.post("/slack/sync", response_model=EnrichResult)
async def sync_slack(db: AsyncSession = Depends(get_db)):
    """Pull Slack users and enrich last_active + license type."""
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.SLACK)
    if not setting or not setting.slack_bot_token_encrypted:
        return EnrichResult(ok=False, message="Slack not configured.")
    token = decrypt(setting.slack_bot_token_encrypted)
    from app.services.enrichment_service import EnrichmentService
    enricher = EnrichmentService(db)
    result = await enricher.enrich_slack(token)
    await db.commit()
    if result.get("ok"):
        return EnrichResult(ok=True, message=f"Synced {result['users_updated']} users from {result['app']}", users_updated=result["users_updated"])
    return EnrichResult(ok=False, message=result.get("error", "Unknown error"))


# ── Zoom ──────────────────────────────────────────────────────────────────

@router.post("/zoom")
async def save_zoom(payload: ZoomSaveRequest, db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.ZOOM)
    if not setting:
        from app.models.integration_setting import IntegrationSetting
        setting = IntegrationSetting(provider=IntegrationProvider.ZOOM)
        db.add(setting)
    setting.zoom_account_id = payload.account_id.strip()
    setting.zoom_client_id = payload.client_id.strip()
    setting.zoom_client_secret_encrypted = encrypt(payload.client_secret.strip())
    await db.commit()
    return {"ok": True, "message": "Zoom credentials saved."}


@router.post("/zoom/test")
async def test_zoom(db: AsyncSession = Depends(get_db)):
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.ZOOM)
    if not setting or not setting.zoom_client_secret_encrypted:
        return {"ok": False, "message": "Zoom not configured."}
    try:
        secret = decrypt(setting.zoom_client_secret_encrypted)
        from app.integrations.zoom.client import ZoomClient
        async with ZoomClient(
            account_id=setting.zoom_account_id,
            client_id=setting.zoom_client_id,
            client_secret=secret,
        ) as zoom:
            me = await zoom.test_connection()
        msg = f"Connected as: {me.get('email', 'unknown')}"
        setting.last_test_ok = True
        setting.last_test_error = None
    except Exception as exc:
        msg = str(exc)
        setting.last_test_ok = False
        setting.last_test_error = msg[:500]
    from datetime import datetime, timezone
    setting.last_tested_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": setting.last_test_ok, "message": msg}


@router.post("/zoom/sync", response_model=EnrichResult)
async def sync_zoom(db: AsyncSession = Depends(get_db)):
    """Pull Zoom users and enrich last_login + license type."""
    svc = IntegrationSettingsService(db)
    setting = await svc.get(IntegrationProvider.ZOOM)
    if not setting or not setting.zoom_client_secret_encrypted:
        return EnrichResult(ok=False, message="Zoom not configured.")
    secret = decrypt(setting.zoom_client_secret_encrypted)
    from app.services.enrichment_service import EnrichmentService
    enricher = EnrichmentService(db)
    result = await enricher.enrich_zoom(
        account_id=setting.zoom_account_id,
        client_id=setting.zoom_client_id,
        client_secret=secret,
    )
    await db.commit()
    if result.get("ok"):
        return EnrichResult(ok=True, message=f"Synced {result['users_updated']} users from {result['app']}", users_updated=result["users_updated"])
    return EnrichResult(ok=False, message=result.get("error", "Unknown error"))
