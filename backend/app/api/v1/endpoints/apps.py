from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models import App, AppStatus
from app.schemas.app import AppCreate, AppUpdate, AppResponse, AppSummary

router = APIRouter(prefix="/apps", tags=["apps"])


@router.get("", response_model=list[AppSummary])
async def list_apps(
    status: AppStatus | None = Query(None),
    category: str | None = Query(None),
    shadow_it: bool | None = Query(None),
    department: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    q = select(App)
    if status:
        q = q.where(App.status == status)
    if category:
        q = q.where(App.category == category)
    if shadow_it is not None:
        q = q.where(App.is_shadow_it == shadow_it)
    if department:
        q = q.where(App.department == department)
    if search:
        q = q.where(App.name.ilike(f"%{search}%") | App.vendor.ilike(f"%{search}%"))
    q = q.order_by(App.name).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=AppResponse, status_code=status.HTTP_201_CREATED)
async def create_app(payload: AppCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(App).where(App.vendor_slug == payload.vendor_slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="App with this vendor_slug already exists")
    app = App(**payload.model_dump())
    db.add(app)
    await db.flush()
    return app


@router.get("/{app_id}", response_model=AppResponse)
async def get_app(app_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


@router.patch("/{app_id}", response_model=AppResponse)
async def update_app(app_id: UUID, payload: AppUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(app, field, value)
    await db.flush()
    return app


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(app_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    await db.delete(app)
