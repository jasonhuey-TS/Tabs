"""Zylo Sync: matching Zylo apps to Tab apps. Saving the token, testing and syncing use the shared /connectors/zylo endpoints."""
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.zylo_links_service import ZyloLinkService

router = APIRouter(prefix="/zylo", tags=["zylo"])


@router.get("/matches")
async def matches(status: str = Query("unmatched"), db: AsyncSession = Depends(get_db)):
    return await ZyloLinkService(db).overview(status)


@router.post("/match")
async def match(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    ok, message = await ZyloLinkService(db).match(payload.get("zylo_id"), payload.get("app_id"))
    return {"ok": ok, "message": message}


@router.post("/status")
async def set_status(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    ok, message = await ZyloLinkService(db).set_status(payload.get("zylo_id"), payload.get("status"))
    return {"ok": ok, "message": message}
