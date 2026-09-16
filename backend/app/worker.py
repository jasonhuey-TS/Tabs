"""
Celery worker — background jobs for scheduled syncs and renewal alerts.
"""
import asyncio
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "saas_manager",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Sync Okta every 6 hours
        "sync-okta": {
            "task": "app.worker.sync_okta_task",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # Sync Azure AD every 6 hours (offset by 1h)
        "sync-azure-ad": {
            "task": "app.worker.sync_azure_ad_task",
            "schedule": crontab(minute=0, hour="1,7,13,19"),
        },
        # Check renewal alerts daily at 08:00 UTC
        "check-renewals": {
            "task": "app.worker.check_renewal_alerts_task",
            "schedule": crontab(minute=0, hour=8),
        },
    },
)


def run_async(coro):
    """Helper to run async code inside a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(name="app.worker.sync_okta_task", bind=True, max_retries=3)
def sync_okta_task(self):
    from app.db.session import AsyncSessionLocal
    from app.services.sync_service import SyncService

    async def _run():
        async with AsyncSessionLocal() as db:
            service = SyncService(db)
            job = await service.sync_okta()
            await db.commit()
            return {"job_id": str(job.id), "status": job.status}

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(name="app.worker.sync_azure_ad_task", bind=True, max_retries=3)
def sync_azure_ad_task(self):
    from app.db.session import AsyncSessionLocal
    from app.services.sync_service import SyncService

    async def _run():
        async with AsyncSessionLocal() as db:
            service = SyncService(db)
            job = await service.sync_azure_ad()
            await db.commit()
            return {"job_id": str(job.id), "status": job.status}

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(name="app.worker.check_renewal_alerts_task")
def check_renewal_alerts_task():
    from app.db.session import AsyncSessionLocal
    from app.services.alert_service import AlertService

    async def _run():
        async with AsyncSessionLocal() as db:
            service = AlertService(db)
            sent = await service.check_and_send_alerts()
            await db.commit()
            return {"alerts_sent": sent}

    return run_async(_run())
