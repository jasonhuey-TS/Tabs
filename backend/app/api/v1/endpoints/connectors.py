"""
Integration Library API.

Every connector is driven by the same handful of endpoints, so adding a connector
never requires a new route. Expected failures (bad credentials, missing fields)
are returned as {"ok": false, "message": ...} so the UI can show the reason.
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import get as get_connector
from app.db.session import AsyncSessionLocal, get_db
from app.services.connector_service import RUNNING, ConnectorService

router = APIRouter(prefix="/connectors", tags=["connectors"])


class SaveRequest(BaseModel):
    values: dict[str, str] = {}
    target_app_id: Optional[str] = None


def _require(key: str):
    connector = get_connector(key)
    if connector is None:
        raise HTTPException(status_code=404, detail="Unknown connector")
    return connector


async def _sync_in_background(key: str) -> None:
    """Runs after the HTTP response is sent, on its own database session."""
    try:
        async with AsyncSessionLocal() as db:
            await ConnectorService(db).sync(key)
    finally:
        RUNNING.discard(key)        # never leave a connector stuck in "running"


@router.get("")
async def list_connectors(db: AsyncSession = Depends(get_db)):
    return await ConnectorService(db).list_state()


@router.get("/{key}/apps")
async def candidate_apps(key: str, q: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    _require(key)
    return await ConnectorService(db).candidate_apps(key, q)


@router.post("/{key}/config")
async def save_config(key: str, payload: SaveRequest, db: AsyncSession = Depends(get_db)):
    connector = _require(key)
    if connector.kind != "app" and not connector.fields:          # a global connector with its own credentials (Zylo) can be configured here too
        raise HTTPException(status_code=400, detail="This connector has nothing to configure")
    svc = ConnectorService(db)
    ok, message = await svc.save_config(key, payload.values, payload.target_app_id)
    return {"ok": ok, "message": message, "connector": await svc.describe(key)}


@router.post("/{key}/test")
async def test_connector(key: str, db: AsyncSession = Depends(get_db)):
    _require(key)
    svc = ConnectorService(db)
    ok, message = await svc.test(key)
    return {"ok": ok, "message": message, "connector": await svc.describe(key)}


@router.post("/{key}/sync")
async def sync_connector(key: str, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    _require(key)
    svc = ConnectorService(db)
    status, message = await svc.begin_sync(key)
    if status == "started":
        background.add_task(_sync_in_background, key)
    return {"ok": status in ("started", "running"), "message": message, "connector": await svc.describe(key)}


@router.post("/{key}/disconnect")
async def disconnect_connector(key: str, db: AsyncSession = Depends(get_db)):
    _require(key)
    svc = ConnectorService(db)
    await svc.disconnect(key)
    return {"ok": True, "message": "Disconnected. Data already synced stays in place.",
            "connector": await svc.describe(key)}
