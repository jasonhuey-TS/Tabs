from fastapi import APIRouter
from app.api.v1.endpoints import apps, contracts, sync, dashboard, settings

api_router = APIRouter()
api_router.include_router(apps.router)
api_router.include_router(contracts.router)
api_router.include_router(sync.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings.router)
