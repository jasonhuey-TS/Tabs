"""The data behind the app screen's Users tab."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.app_activity_service import AppActivityService

router = APIRouter(prefix="/app-activity", tags=["app-activity"])


@router.get("/{app_id}")
async def app_activity(app_id: str, db: AsyncSession = Depends(get_db)):
    data = await AppActivityService(db).get(app_id)
    if data is None:
        raise HTTPException(status_code=404, detail="App not found")
    return data


@router.post("/{app_id}/import/preview")
async def import_preview(app_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """What filling in last-activity dates from a file would change. Writes nothing."""
    return await AppActivityService(db).import_preview(app_id, payload.get("text"), payload.get("mapping"))


@router.post("/{app_id}/import/commit")
async def import_commit(app_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return await AppActivityService(db).import_commit(app_id, payload.get("text"), payload.get("mapping"), payload.get("file_name") or "upload.csv")

