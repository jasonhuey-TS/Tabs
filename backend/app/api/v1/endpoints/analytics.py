"""Portfolio-wide analytics for the Analytics page."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/portfolio")
async def portfolio(db: AsyncSession = Depends(get_db)):
    return await AnalyticsService(db).portfolio()
