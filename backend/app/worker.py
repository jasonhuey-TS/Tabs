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
        "sync-okta": {
            "task": "app.worker.sync_okta_task",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "sync-azure-ad": {
            "task": "app.worker.sync_azure_ad_task",
            "schedule": crontab(minute=0, hour="1,7,13,19"),
        },
        "check-renewals": {
            "task": "app.worker.check_renewal_alerts_task",
            "schedule": crontab(minute=0, hour=8),
        },
    },
)


def run_async(coro):
    """Python 3.11+ compatible async runner for Celery tasks."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop is closed")
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No running loop or closed loop — create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
            asyncio.set_event_loop(None)


@celery_app.task(name="app.worker.sync_okta_task", bind=True, max_retries=3)
def sync_okta_task(self):
    from app.db.session import AsyncSessionLocal
    from app.services.sync_service import SyncService

    async def _run():
        async with AsyncSessionLocal() as db:
            service = SyncService(db)
            job = await service.sync_okta()
            await db.commit()
            return {"job_id": str(job.id), "status": str(job.status)}

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
            return {"job_id": str(job.id), "status": str(job.status)}

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
