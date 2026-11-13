"""Shadow IT: apps people connected to their Google or Microsoft work account. Running discovery uses the shared /connectors/app_discovery endpoints."""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.discovery_service import DiscoveryService

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/apps")
async def apps(status: str = Query("new"), source: str | None = None, risk: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db)):
    return await DiscoveryService(db).overview(status, source, risk, q)


@router.get("/people")
async def people(source: str, external_id: str, db: AsyncSession = Depends(get_db)):
    result = await DiscoveryService(db).people(source, external_id)
    if result is None:
        raise HTTPException(status_code=404, detail="That app isn't on the list any more.")
    return result


@router.post("/act")
async def act(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    ok, message = await DiscoveryService(db).act(payload.get("source"), payload.get("external_id"), payload.get("action"), payload.get("app_id"))
    return {"ok": ok, "message": message}
