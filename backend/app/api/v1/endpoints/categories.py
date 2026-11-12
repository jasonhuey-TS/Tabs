"""App categories and functions: coverage, a CSV of the current labels, and importing labels from another tool's export."""
from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.categories_service import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    return await CategoryService(db).summary()


@router.get("/export.csv")
async def export_csv(db: AsyncSession = Depends(get_db)):
    return Response(content=await CategoryService(db).export_csv(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="app-categories.csv"'})


@router.post("/import/preview")
async def import_preview(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return await CategoryService(db).preview(payload.get("text"), payload.get("mapping"), payload.get("value_map"), payload.get("decisions"), payload.get("overwrite", False))


@router.post("/import/commit")
async def import_commit(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return await CategoryService(db).commit(payload.get("text"), payload.get("mapping"), payload.get("value_map"), payload.get("decisions"),
                                            payload.get("overwrite", False), payload.get("file_name") or "upload.csv")
