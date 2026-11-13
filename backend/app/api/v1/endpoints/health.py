"""Data health: how complete the information about your apps is, and where to improve it."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    return await HealthService(db).overview()


@router.get("/missing")
async def missing(check: str, limit: int = Query(200, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    result = await HealthService(db).missing(check, limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown check.")
    return result
