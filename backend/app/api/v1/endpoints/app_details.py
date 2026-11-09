"""API for the app screen's tabs. Reads return data (404 for an unknown app); writes return {ok, message}."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.app_details_service import AppDetailsService

router = APIRouter(prefix="/app-details", tags=["app-details"])
roster_router = APIRouter(prefix="/employee-roster", tags=["app-details"])


def _found(value):
    if value is None:
        raise HTTPException(status_code=404, detail="App not found")
    return value


def _done(result):
    ok, message = result
    return {"ok": ok, "message": message}


@router.get("/{app_id}/settings")
async def get_settings(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).get_settings(app_id))


@router.post("/{app_id}/settings")
async def save_settings(app_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return _done(await AppDetailsService(db).save_settings(app_id, payload))


@router.get("/{app_id}/contracts")
async def contracts(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).contracts(app_id))


@router.get("/{app_id}/savings")
async def savings(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).savings(app_id))


@router.get("/{app_id}/payments")
async def payments(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).payments(app_id))


@router.post("/{app_id}/payments")
async def add_payment(app_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return _done(await AppDetailsService(db).add_payment(app_id, payload))


@router.post("/{app_id}/payments/{payment_id}/delete")
async def delete_payment(app_id: str, payment_id: str, db: AsyncSession = Depends(get_db)):
    return {"ok": await AppDetailsService(db).delete_payment(app_id, payment_id)}


@router.get("/{app_id}/documents")
async def documents(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).documents(app_id))


@router.post("/{app_id}/documents")
async def add_document(app_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return _done(await AppDetailsService(db).add_document(app_id, payload))


@router.post("/{app_id}/documents/{doc_id}/delete")
async def delete_document(app_id: str, doc_id: str, db: AsyncSession = Depends(get_db)):
    return {"ok": await AppDetailsService(db).delete_document(app_id, doc_id)}


@router.get("/{app_id}/sentiment")
async def sentiment(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).sentiment(app_id))


@router.post("/{app_id}/sentiment")
async def add_feedback(app_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return _done(await AppDetailsService(db).add_feedback(app_id, payload))


@router.post("/{app_id}/sentiment/{feedback_id}/delete")
async def delete_feedback(app_id: str, feedback_id: str, db: AsyncSession = Depends(get_db)):
    return {"ok": await AppDetailsService(db).delete_feedback(app_id, feedback_id)}


@router.get("/{app_id}/history")
async def history(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).history(app_id))


@router.get("/{app_id}/alerts")
async def alerts(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).alerts(app_id))


@router.get("/{app_id}/filters")
async def saved_filters(app_id: str, db: AsyncSession = Depends(get_db)):
    return _found(await AppDetailsService(db).saved_filters(app_id))


@router.post("/{app_id}/filters")
async def add_saved_filter(app_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return _done(await AppDetailsService(db).add_saved_filter(app_id, payload))


@router.post("/filters/{filter_id}/delete")
async def delete_saved_filter(filter_id: str, db: AsyncSession = Depends(get_db)):
    return {"ok": await AppDetailsService(db).delete_saved_filter(filter_id)}


@roster_router.get("")
async def roster_status(db: AsyncSession = Depends(get_db)):
    return {"count": await AppDetailsService(db).roster_count()}


@roster_router.post("")
async def replace_roster(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    ok, message, count = await AppDetailsService(db).replace_roster(str(payload.get("text") or ""))
    return {"ok": ok, "message": message, "count": count}
