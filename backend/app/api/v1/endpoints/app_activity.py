"""The data behind the app screen's Users tab."""
from fastapi import APIRouter, Depends, HTTPException
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
