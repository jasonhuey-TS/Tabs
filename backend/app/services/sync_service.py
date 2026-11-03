"""
Sync service — pulls apps, users and app assignments from Okta / Azure AD.

Okta assignments
----------------
Okta's /apps/{id}/users endpoint returns everyone with access to an app,
including people who only have it because they belong to a broad group such as
"All-Employee". That makes an app like Zoom look like it has ~1,100 users.

To show who actually uses an app, we build each app's user list from:
  * users assigned to the app directly, plus
  * members of the groups assigned to the app,
ignoring the broad groups in EXCLUDED_GROUPS -- but only when the app also has
at least one narrower group. If an app is assigned *only* to a broad group,
everyone really does have it, so we keep that group.

Exception: apps in LICENSE_CONNECTOR_APPS (Zoom, Slack). Their connector reports
each person's license (e.g. Zoom Basic vs Licensed), so there we keep everyone
Okta says is assigned and let the license data decide who counts.
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

# Seconds to pause after each Okta request, to stay under Okta's rate limits.
REQUEST_DELAY = 0.2

# Okta group names (case-insensitive) treated as "everyone" groups.
# Add more names here to ignore other broad groups.
EXCLUDED_GROUPS = {"all-employee"}

# App names (case-insensitive) whose connector supplies per-user license info.
# For these we do NOT narrow by Okta group.
LICENSE_CONNECTOR_APPS = {"zoom", "slack"}


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


async def _okta_get(okta, path, params=None):
    """GET a (paginated) Okta list endpoint with retry and pacing."""
    result = await _with_retry(lambda: okta._paginate(path, params=params))
    await asyncio.sleep(REQUEST_DELAY)
    return result


async def _okta_assigned_ids(okta, okta_app_id: str, group_cache: dict,
                             keep_broad_groups: bool = False) -> set:
    """Return the Okta user IDs that should count as using this app."""
    app_users = await _okta_get(okta, f"/apps/{okta_app_id}/users", {"limit": 500})
    if not app_users:
        return set()

    # Anyone whose assignment is not group-based was assigned directly.
    direct = {u["id"] for u in app_users if u.get("scope") != "GROUP"}

    # No group-based assignments -> nothing more to look up.
    if not any(u.get("scope") == "GROUP" for u in app_users):
        return direct

    groups = await _okta_get(okta, f"/apps/{okta_app_id}/groups", {"expand": "group"})
    assigned = []
    for g in groups:
        name = g.get("_embedded", {}).get("group", {}).get("profile", {}).get("name") or ""
        assigned.append((g["id"], name))

    narrow = [g for g in assigned if g[1].strip().lower() not in EXCLUDED_GROUPS]
    # Keep broad groups if told to, or if they are the app's only groups.
    use_groups = assigned if keep_broad_groups else (narrow or assigned)

    ids = set(direct)
    for gid, _name in use_groups:
        if gid not in group_cache:
            members = await _okta_get(okta, f"/groups/{gid}/users", {"limit": 200})
            group_cache[gid] = {m["id"] for m in members}
        ids |= group_cache[gid]
    return ids


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

                # Step 1: apps. Okta apps that share a name map to one app here.
                raw_apps = await okta.list_apps()
                job.apps_discovered = len(raw_apps)
                app_objs = {}      # App.id -> App
                raw_by_app = {}    # App.id -> [raw Okta apps]
                for raw_app in raw_apps:
                    app, created = await self._upsert_app(normalize_okta_app(raw_app))
                    app_objs[app.id] = app
                    raw_by_app.setdefault(app.id, []).append(raw_app)
                    if created:
                        job.apps_created += 1
                    else:
                        job.apps_updated += 1
                await self.db.flush()
                log.info("okta.apps.done", count=len(raw_apps))

                # Step 2: active users (one pass), mapped Okta user ID -> User.id
                raw_users = await okta.list_users()
                existing = {u.email: u for u in (await self.db.execute(select(User))).scalars().all()}
                okta_to_user = {}
                for raw_user in raw_users:
                    profile = raw_user.get("profile", {})
                    email = profile.get("email") or profile.get("login", "")
                    if not email:
                        continue
                    user = existing.get(email)
                    if not user:
                        display_name = (
                            profile.get("displayName")
                            or (profile.get("firstName", "") + " " + profile.get("lastName", "")).strip()
                            or email
                        )
                        user = User(email=email, full_name=display_name)
                        self.db.add(user)
                        existing[email] = user
                    okta_to_user[raw_user["id"]] = user
                await self.db.flush()
                okta_to_user_id = {oid: u.id for oid, u in okta_to_user.items()}
                log.info("okta.users.done", count=len(okta_to_user_id))

                # Step 3: per-app assignments
                errors = 0
                total_assignments = 0
                group_cache = {}   # Okta group ID -> set of member Okta user IDs
                for n, (app_id, raws) in enumerate(raw_by_app.items()):
                    keep_broad = app_objs[app_id].name.strip().lower() in LICENSE_CONNECTOR_APPS
                    try:
                        okta_ids = set()
                        for raw_app in raws:
                            okta_ids |= await _okta_assigned_ids(
                                okta, raw_app["id"], group_cache, keep_broad_groups=keep_broad)
                    except Exception as exc:
                        # Leave this app's existing assignments untouched.
                        log.warning("okta.assignments.failed",
                                    app=app_objs[app_id].name, error=str(exc)[:150])
                        errors += 1
                        continue

                    wanted = {okta_to_user_id[i] for i in okta_ids if i in okta_to_user_id}
                    await self._apply_assignments(app_objs[app_id], wanted)
                    total_assignments += len(wanted)

                    if n % 50 == 0:
                        log.info("okta.assignments.progress", done=n, total=len(raw_by_app))

                job.users_synced = total_assignments   # total assignments, not unique users
                job.errors = errors
                job.status = SyncJobStatus.PARTIAL if errors else SyncJobStatus.COMPLETED
                log.info("okta.sync.done", apps=job.apps_discovered,
                         assignments=total_assignments, errors=errors)

        except Exception as exc:
            log.error("sync.okta.failed", error=str(exc))
            job.status = SyncJobStatus.FAILED
            job.error_detail = {"error": str(exc)}
            job.errors += 1

        job.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return job

    async def _apply_assignments(self, app: App, wanted_user_ids: set) -> None:
        """Make the app's user list match wanted_user_ids, keeping rows that
        are still valid so last-active / license data from connectors survives."""
        rows = await self.db.execute(select(AppUser.user_id).where(AppUser.app_id == app.id))
        current = set(rows.scalars().all())

        to_remove = current - wanted_user_ids
        to_add = wanted_user_ids - current

        if to_remove:
            await self.db.execute(
                delete(AppUser).where(AppUser.app_id == app.id, AppUser.user_id.in_(list(to_remove)))
            )
        for user_id in to_add:
            self.db.add(AppUser(app_id=app.id, user_id=user_id))
        await self.db.flush()

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
