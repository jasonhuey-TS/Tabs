from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.session import get_db
from app.models import SyncJob, SyncSource
from app.schemas.sync import SyncJobResponse, ImportResponse

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/okta", response_model=SyncJobResponse)
async def trigger_okta_sync(db: AsyncSession = Depends(get_db)):
    """Manually trigger an Okta sync (also runs on schedule)."""
    from app.worker import sync_okta_task
    sync_okta_task.delay()
    # Return the most recent job record (created by the task)
    result = await db.execute(
        select(SyncJob).where(SyncJob.source == SyncSource.OKTA).order_by(desc(SyncJob.created_at)).limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=202, detail="Sync triggered — check back shortly")
    return job


@router.post("/azure-ad", response_model=SyncJobResponse)
async def trigger_azure_ad_sync(db: AsyncSession = Depends(get_db)):
    """Manually trigger an Azure AD sync."""
    from app.worker import sync_azure_ad_task
    sync_azure_ad_task.delay()
    result = await db.execute(
        select(SyncJob).where(SyncJob.source == SyncSource.AZURE_AD).order_by(desc(SyncJob.created_at)).limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=202, detail="Sync triggered — check back shortly")
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
    file: UploadFile = File(...),
    import_type: str = Form(..., description="apps | licenses | contracts"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV file to bulk-import apps, licenses, or contracts."""
    from app.services.import_service import ImportService

    if import_type not in ("apps", "licenses", "contracts"):
        raise HTTPException(status_code=400, detail="import_type must be apps, licenses, or contracts")

    content = await file.read()
    service = ImportService(db)
    record = await service.import_csv(content, import_type, file.filename)
    return record
