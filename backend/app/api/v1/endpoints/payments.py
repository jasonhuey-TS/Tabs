"""The Payments page (Financial Data): totals across apps, saved views, and loading payments from a file."""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.app_details_service import AppDetailsService
from app.services.payments_service import PaymentsService

router = APIRouter(prefix="/payments", tags=["payments"])


def filters(q: Optional[str] = None, type: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
            source: Optional[str] = None, app_id: Optional[str] = None) -> dict:
    return {"q": q, "type": type, "date_from": date_from, "date_to": date_to, "source": source, "app_id": app_id}


@router.get("/summary")
async def summary(f: dict = Depends(filters), db: AsyncSession = Depends(get_db)):
    return await PaymentsService(db).summary(f)


@router.get("/export.csv")
async def export_csv(f: dict = Depends(filters), db: AsyncSession = Depends(get_db)):
    return Response(content=await PaymentsService(db).export_csv(f), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="payments.csv"'})


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    return {"fiscal_year_start_month": await PaymentsService(db).fiscal_month()}


@router.post("/settings")
async def save_settings(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    ok, message = await PaymentsService(db).save_fiscal_month(payload.get("fiscal_year_start_month"))
    return {"ok": ok, "message": message}


@router.get("/filters")
async def saved_filters(db: AsyncSession = Depends(get_db)):
    return await PaymentsService(db).saved_filters()


@router.post("/filters")
async def add_saved_filter(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    ok, message = await PaymentsService(db).add_saved_filter(payload)
    return {"ok": ok, "message": message}


@router.post("/filters/{filter_id}/delete")
async def delete_saved_filter(filter_id: str, db: AsyncSession = Depends(get_db)):
    return {"ok": await PaymentsService(db).delete_saved_filter(filter_id)}


@router.get("/app/{app_id}")
async def for_app(app_id: str, f: dict = Depends(filters), db: AsyncSession = Depends(get_db)):
    return await PaymentsService(db).for_app(app_id, f)


@router.post("/add")
async def add_payment(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    ok, message = await AppDetailsService(db).add_payment(str(payload.get("app_id") or ""), payload)
    return {"ok": ok, "message": message}


@router.post("/import/preview")
async def import_preview(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return await PaymentsService(db).import_preview(payload.get("text"), payload.get("mapping"), payload.get("default_type", "ap"), payload.get("decisions"))


@router.post("/import/commit")
async def import_commit(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return await PaymentsService(db).import_commit(payload.get("text"), payload.get("mapping"), payload.get("default_type", "ap"),
                                                   payload.get("decisions"), payload.get("file_name") or "upload.csv")


@router.post("/{payment_id}/delete")
async def delete_payment(payment_id: str, db: AsyncSession = Depends(get_db)):
    if not await PaymentsService(db).delete(payment_id):
        raise HTTPException(status_code=404, detail="Unknown payment")
    return {"ok": True}
