"""
Sync service — correctly syncs only users assigned to each specific Okta app.
Uses per-app user fetching with rate limit handling.
"""
import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models import App, AppUser, User, SyncJob, SyncJobStatus, SyncSource
from app.integrations.okta.client import OktaClient, normalize_okta_app
from app.integrations.azure_ad.client import AzureADClient, normalize_azure_app

log = structlog.get_logger()

# Okta rate limit: ~600 requests/min for most endpoints
# We'll pace at 1 request per 200ms = 300/min to be safe
REQUEST_DELAY = 0.2  # seconds between per-app user requests


async def _with_retry(coro_fn, retries=4, base_delay=5.0):
    """Retry on 429 with exponential backoff."""
    for attempt in range(retries):
        try:
            return await coro_fn()
        except Exception as exc:
            if "429" in str(exc) and attempt < retries - 1:
                wait = base_delay * (2 ** attempt)
                log.warning("rate_limited.waiting", attempt=attempt + 1, wait=wait)
                await asyncio.sleep(wait)
            else:
                raise


class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_okta(self) -> SyncJob:
        job = SyncJob(source=SyncSource.OKTA, status=SyncJobStatus.RUNNING, started_at=datetime.now(timezone.utc))
        self.db.add(job)
        await self.db.flush()

        try:
            from app.models.integration_setting import IntegrationProvider
            from app.services.integration_settings_service import IntegrationSettingsService
            svc = IntegrationSettingsService(self.db)
            db_setting = await svc.get(IntegrationProvider.OKTA)
            okta_domain = (db_setting.okta_domain if db_setting else None) or None
            okta_token = (svc.get_okta_token(db_setting) if db_setting else None) or None

            async with OktaClient(domain=okta_domain, api_token=okta_token) as okta:

                # Step 1: sync all apps
                raw_apps = await okta.list_apps()
                job.apps_discovered = len(raw_apps)
                log.info("okta.apps.done", count=len(raw_apps))

                app_id_map = {}  # okta_app_id -> App DB object
                for raw_app in raw_apps:
                    normalized = normalize_okta_app(raw_app)
                    app, created = await self._upsert_app(normalized)
                    app_id_map[raw_app["id"]] = app
                    if created:
                        job.apps_created += 1
                    else:
                        job.apps_updated += 1

                # Commit apps before processing users
                await self.db.flush()

                # Step 2: for each app, fetch ONLY its assigned users
                log.info("okta.assignments.start", total_apps=len(raw_apps))
                assignment_errors = 0

                for i, raw_app in enumerate(raw_apps):
                    app = app_id_map.get(raw_app["id"])
                    if not app:
                        continue

                    try:
                        # Rate limit: pause every request
                        if i > 0:
                            await asyncio.sleep(REQUEST_DELAY)

                        # Fetch users assigned specifically to this app
                        raw_app_users = await _with_retry(
                            lambda app_id=raw_app["id"]: okta.list_app_users(app_id),
                        )

                        # Clear existing app-user links for this app
                        # so we get a clean accurate picture
                        await self.db.execute(
                            delete(AppUser).where(AppUser.app_id == app.id)
                        )

                        # Re-create with current assignments
                        for raw_user in raw_app_users:
                            profile = raw_user.get("profile", {})
                            email = profile.get("email") or profile.get("login", "")
                            if not email:
                                continue
                            display_name = (
                                profile.get("displayName") or
                                (profile.get("firstName", "") + " " + profile.get("lastName", "")).strip() or
                                email
                            )
                            user = await self._get_or_create_user(email, display_name)
                            await self._upsert_app_user(app, user)
                            job.users_synced += 1

                        if i % 50 == 0:
                            log.info("okta.assignments.progress", done=i, total=len(raw_apps))
                            await self.db.flush()

                    except Exception as exc:
                        log.warning("okta.app_users.failed",
                                    app=raw_app.get("label"),
                                    error=str(exc)[:150])
                        assignment_errors += 1
                        continue

                await self.db.flush()

                if assignment_errors > 0:
                    job.errors = assignment_errors
                    job.status = SyncJobStatus.PARTIAL
                    log.warning("okta.assignments.partial", errors=assignment_errors)
                else:
                    job.status = SyncJobStatus.COMPLETED

                log.info("okta.sync.done",
                         apps=job.apps_discovered,
                         users=job.users_synced,
                         errors=assignment_errors)

        except Exception as exc:
            log.error("sync.okta.failed", error=str(exc))
            job.status = SyncJobStatus.FAILED
            job.error_detail = {"error": str(exc)}
            job.errors += 1

        job.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    async def sync_azure_ad(self) -> SyncJob:
        job = SyncJob(source=SyncSource.AZURE_AD, status=SyncJobStatus.RUNNING, started_at=datetime.now(timezone.utc))
        self.db.add(job)
        await self.db.flush()

        try:
            from app.models.integration_setting import IntegrationProvider
            from app.services.integration_settings_service import IntegrationSettingsService
            svc = IntegrationSettingsService(self.db)
            db_setting = await svc.get(IntegrationProvider.AZURE_AD)
            tenant_id = (db_setting.azure_tenant_id if db_setting else None) or None
            client_id = (db_setting.azure_client_id if db_setting else None) or None
            client_secret = (svc.get_azure_secret(db_setting) if db_setting else None) or None

            async with AzureADClient(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            ) as az:
                service_principals = await az.list_service_principals()
                job.apps_discovered = len(service_principals)

                for sp in service_principals:
                    normalized = normalize_azure_app(sp)
                    app, created = await self._upsert_app(normalized)
                    if created:
                        job.apps_created += 1
                    else:
                        job.apps_updated += 1

                    try:
                        assignments = await az.list_app_role_assignments(sp["id"])
                        await self.db.execute(delete(AppUser).where(AppUser.app_id == app.id))
                        for assignment in assignments:
                            principal_email = assignment.get("principalDisplayName", "")
                            if not principal_email or assignment.get("principalType") != "User":
                                continue
                            user = await self._get_or_create_user(principal_email, principal_email)
                            await self._upsert_app_user(app, user)
                            job.users_synced += 1
                    except Exception:
                        continue

            job.status = SyncJobStatus.COMPLETED

        except Exception as exc:
            log.error("sync.azure_ad.failed", error=str(exc))
            job.status = SyncJobStatus.FAILED
            job.error_detail = {"error": str(exc)}
            job.errors += 1

        job.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    async def _upsert_app(self, data: dict) -> tuple:
        result = await self.db.execute(select(App).where(App.vendor_slug == data["vendor_slug"]))
        app = result.scalar_one_or_none()
        created = False
        if not app:
            app = App(**{k: v for k, v in data.items() if k != "meta"})
            self.db.add(app)
            created = True
        else:
            app.last_seen_at = datetime.now(timezone.utc)
        await self.db.flush()
        return app, created

    async def _get_or_create_user(self, email: str, full_name: str) -> User:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            user = User(email=email, full_name=full_name or email)
            self.db.add(user)
            await self.db.flush()
        return user

    async def _upsert_app_user(self, app: App, user: User, last_login=None) -> AppUser:
        result = await self.db.execute(
            select(AppUser).where(AppUser.app_id == app.id, AppUser.user_id == user.id)
        )
        app_user = result.scalar_one_or_none()
        if not app_user:
            app_user = AppUser(app_id=app.id, user_id=user.id)
            self.db.add(app_user)
        if last_login:
            app_user.last_login_at = last_login
        await self.db.flush()
        return app_user
