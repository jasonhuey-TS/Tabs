"""
Sync service — orchestrates IdP data pulls, deduplication, and DB writes.

Strategy:
- Fetch all apps in one call (fast)
- Fetch all users in one call (fast)
- Skip per-app user assignment fetching (avoids Okta rate limits on 627 apps)
- Future: use Okta System Log API for incremental user-app mapping
"""
import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import App, AppUser, User, SyncJob, SyncJobStatus, SyncSource
from app.integrations.okta.client import OktaClient, normalize_okta_app
from app.integrations.azure_ad.client import AzureADClient, normalize_azure_app

log = structlog.get_logger()


class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ #
    # Okta                                                                 #
    # ------------------------------------------------------------------ #

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
                # Step 1: sync all apps (one API call)
                raw_apps = await okta.list_apps()
                job.apps_discovered = len(raw_apps)

                for raw_app in raw_apps:
                    normalized = normalize_okta_app(raw_app)
                    app, created = await self._upsert_app(normalized)
                    if created:
                        job.apps_created += 1
                    else:
                        job.apps_updated += 1

                # Step 2: sync all users (one API call)
                log.info("okta.list_users.start")
                raw_users = await okta.list_users()
                log.info("okta.list_users.done", count=len(raw_users))

                for raw_user in raw_users:
                    profile = raw_user.get("profile", {})
                    email = profile.get("email") or profile.get("login", "")
                    if not email:
                        continue
                    display_name = profile.get("displayName") or profile.get("firstName", "") + " " + profile.get("lastName", "")
                    display_name = display_name.strip() or email
                    await self._get_or_create_user(email, display_name)
                    job.users_synced += 1

            job.status = SyncJobStatus.COMPLETED
        except Exception as exc:
            log.error("sync.okta.failed", error=str(exc))
            job.status = SyncJobStatus.FAILED
            job.error_detail = {"error": str(exc)}
            job.errors += 1

        job.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    # ------------------------------------------------------------------ #
    # Azure AD                                                             #
    # ------------------------------------------------------------------ #

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
                # Step 1: sync all service principals (apps)
                service_principals = await az.list_service_principals()
                job.apps_discovered = len(service_principals)

                for sp in service_principals:
                    normalized = normalize_azure_app(sp)
                    app, created = await self._upsert_app(normalized)
                    if created:
                        job.apps_created += 1
                    else:
                        job.apps_updated += 1

                # Step 2: sync all users (one API call)
                raw_users = await az.list_users()
                for raw_user in raw_users:
                    email = raw_user.get("mail") or raw_user.get("userPrincipalName", "")
                    if not email:
                        continue
                    display_name = raw_user.get("displayName") or email
                    await self._get_or_create_user(email, display_name)
                    job.users_synced += 1

            job.status = SyncJobStatus.COMPLETED
        except Exception as exc:
            log.error("sync.azure_ad.failed", error=str(exc))
            job.status = SyncJobStatus.FAILED
            job.error_detail = {"error": str(exc)}
            job.errors += 1

        job.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    async def _upsert_app(self, data: dict) -> tuple[App, bool]:
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

    async def _upsert_app_user(self, app: App, user: User, last_login: datetime | None = None) -> AppUser:
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
