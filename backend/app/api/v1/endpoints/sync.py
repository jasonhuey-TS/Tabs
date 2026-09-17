from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.session import get_db
from app.models import SyncJob, SyncSource
from app.schemas.sync import SyncJobResponse, ImportResponse

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/okta", response_model=SyncJobResponse)
async def trigger_okta_sync(db: AsyncSession = Depends(get_db)):
    """Trigger an Okta sync — runs directly in the API for reliability."""
    from app.services.sync_service import SyncService
    service = SyncService(db)
    job = await service.sync_okta()
    return job


@router.post("/azure-ad", response_model=SyncJobResponse)
async def trigger_azure_ad_sync(db: AsyncSession = Depends(get_db)):
    """Trigger an Azure AD sync — runs directly in the API for reliability."""
    from app.services.sync_service import SyncService
    service = SyncService(db)
    job = await service.sync_azure_ad()
    return job


@router.get("/jobs", response_model=list[SyncJobResponse])
async def list_sync_jobs(
    source: SyncSource | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    q = select(SyncJob).order_by(desc(SyncJob.created_at)).limit(limit)
    if source:
        q = q.where(SyncJob.source == source)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/import/csv", response_model=ImportResponse)
async def import_csv(
    file=None,
    import_type: str = "apps",
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV file to bulk-import apps, licenses, or contracts."""
    from fastapi import UploadFile, File, Form
    from app.services.import_service import ImportService

    if import_type not in ("apps", "licenses", "contracts"):
        raise HTTPException(status_code=400, detail="import_type must be apps, licenses, or contracts")

    content = await file.read()
    service = ImportService(db)
    record = await service.import_csv(content, import_type, file.filename)
    return record
