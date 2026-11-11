from fastapi import APIRouter
from app.api.v1.endpoints import apps, contracts, sync, dashboard, settings, integrations, connectors, reclamation, app_activity, app_details, payments, app_icons

api_router = APIRouter()
api_router.include_router(apps.router)
api_router.include_router(contracts.router)
api_router.include_router(sync.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings.router)
api_router.include_router(integrations.router)
api_router.include_router(connectors.router)
api_router.include_router(reclamation.router)
api_router.include_router(app_activity.router)
api_router.include_router(app_details.router)
api_router.include_router(app_details.roster_router)
api_router.include_router(payments.router)
api_router.include_router(app_icons.router)
