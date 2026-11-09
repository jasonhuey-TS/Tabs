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

Exception: apps covered by an Integration Library connector. The connector reports
each person's license (e.g. Zoom Basic vs Licensed), so there we keep everyone
Okta says is assigned and let the license data decide who counts.
"""
import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models import App, AppUser, User, SyncJob, SyncJobStatus, SyncSource
from app.models.user_profile import UserProfile
from app.services.app_events import record_event
from app.integrations.okta.client import OktaClient, normalize_okta_app
from app.integrations.azure_ad.client import AzureADClient, normalize_azure_app

log = structlog.get_logger()

# Seconds to pause after each Okta request, to stay under Okta's rate limits.
REQUEST_DELAY = 0.2

# Okta group names (case-insensitive) treated as "everyone" groups.
# Add more names here to ignore other broad groups.
EXCLUDED_GROUPS = {"all-employee"}

# Fallback list of apps whose connector supplies per-user license info.
LICENSE_CONNECTOR_APPS = {"zoom", "slack"}


def _has_license_connector(app_name: str) -> bool:
    """True if an Integration Library connector covers this app. Such apps keep
    everyone Okta says is assigned; the connector's license data decides who counts."""
    name = (app_name or "").strip().lower()
    try:
        from app.connectors import all_connectors
        return any(alias in name for c in all_connectors() if c.kind == "app" for alias in c.app_aliases)
    except Exception:
        return name in LICENSE_CONNECTOR_APPS


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


def _okta_time(value):
    """Okta timestamp -> aware datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# Okta profile attribute -> user_profiles column
PROFILE_FIELDS = {"first_name": "firstName", "last_name": "lastName", "title": "title", "department": "department",
                  "cost_center": "costCenter", "division": "division", "organization": "organization",
                  "employee_type": "employeeType"}


def profile_fields(profile: dict, raw_user: dict | None = None) -> dict:
    """The org details we keep from an Okta user; blanks become None."""
    out = {}
    for column, key in PROFILE_FIELDS.items():
        value = (profile or {}).get(key)
        text = str(value).strip()[:255] if value not in (None, "") else ""
        out[column] = text or None
    raw_user = raw_user or {}
    out["okta_id"] = (str(raw_user.get("id")).strip()[:255] or None) if raw_user.get("id") else None
    out["okta_status"] = (str(raw_user.get("status")).strip()[:50] or None) if raw_user.get("status") else None
    return out


def _merge_assignments(into: dict, found: dict) -> None:
    """Merge {okta_user_id: assigned_on} maps, keeping the earliest known assignment date."""
    for oid, assigned_on in found.items():
        prev = into.get(oid)
        into[oid] = min(prev, assigned_on) if prev and assigned_on else (prev or assigned_on)


async def _okta_assigned_ids(okta, okta_app_id: str, group_cache: dict,
                             keep_broad_groups: bool = False) -> dict:
    """Return {Okta user ID: assignment date or None} for people who should count as using this app."""
    app_users = await _okta_get(okta, f"/apps/{okta_app_id}/users", {"limit": 500})
    if not app_users:
        return {}
    assigned_on = {u["id"]: _okta_time(u.get("created")) for u in app_users}

    # Anyone whose assignment is not group-based was assigned directly.
    direct = {u["id"] for u in app_users if u.get("scope") != "GROUP"}

    # No group-based assignments -> nothing more to look up.
    if not any(u.get("scope") == "GROUP" for u in app_users):
        return {i: assigned_on.get(i) for i in direct}

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
    return {i: assigned_on.get(i) for i in ids}


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
                okta_to_user, okta_profiles = {}, {}
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
                    okta_profiles[raw_user["id"]] = profile_fields(profile, raw_user)
                await self.db.flush()
                await self._upsert_profiles({okta_to_user[oid].id: fields for oid, fields in okta_profiles.items()})
                okta_to_user_id = {oid: u.id for oid, u in okta_to_user.items()}
                log.info("okta.users.done", count=len(okta_to_user_id))

                # Step 3: per-app assignments
                errors = 0
                total_assignments = 0
                group_cache = {}   # Okta group ID -> set of member Okta user IDs
                for n, (app_id, raws) in enumerate(raw_by_app.items()):
                    keep_broad = _has_license_connector(app_objs[app_id].name)
                    try:
                        okta_ids = {}
                        for raw_app in raws:
                            found = await _okta_assigned_ids(
                                okta, raw_app["id"], group_cache, keep_broad_groups=keep_broad)
                            _merge_assignments(okta_ids, found)
                    except Exception as exc:
                        # Leave this app's existing assignments untouched.
                        log.warning("okta.assignments.failed",
                                    app=app_objs[app_id].name, error=str(exc)[:150])
                        errors += 1
                        continue

                    wanted = {okta_to_user_id[i]: assigned_on
                              for i, assigned_on in okta_ids.items() if i in okta_to_user_id}
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

    async def _upsert_profiles(self, by_user_id: dict) -> None:
        """Store each person's org details. Best effort: a problem here must never break the sync, so it runs
        in its own savepoint and is only logged."""
        try:
            async with self.db.begin_nested():
                existing = {p.user_id: p for p in (await self.db.execute(select(UserProfile))).scalars().all()}
                for user_id, fields in by_user_id.items():
                    row = existing.get(user_id)
                    if row is None:
                        self.db.add(UserProfile(user_id=user_id, **fields))
                        continue
                    for column, value in fields.items():
                        if getattr(row, column) != value:
                            setattr(row, column, value)
        except Exception as exc:
            log.warning("okta.profiles.failed", error=str(exc))

    async def _apply_assignments(self, app: App, wanted) -> None:
        """Make the app's user list match `wanted` ({user_id: assignment date}), keeping rows
        that are still valid so last-active / license data from connectors survives."""
        if not isinstance(wanted, dict):
            wanted = dict.fromkeys(wanted)
        rows = await self.db.execute(select(AppUser.user_id, AppUser.provisioned_at).where(AppUser.app_id == app.id))
        current = {user_id: provisioned for user_id, provisioned in rows.all()}

        to_remove = set(current) - set(wanted)
        to_add = set(wanted) - set(current)
        backfill = [u for u in set(current) & set(wanted) if current[u] is None and wanted[u] is not None]

        if to_add or to_remove:
            parts = ([f"{len(to_add):,} assigned"] if to_add else []) + ([f"{len(to_remove):,} removed"] if to_remove else [])
            await record_event(self.db, app.id, "assignments", "Okta sync: " + ", ".join(parts))
        if to_remove:
            await self.db.execute(
                delete(AppUser).where(AppUser.app_id == app.id, AppUser.user_id.in_(list(to_remove)))
            )
        for user_id in to_add:
            self.db.add(AppUser(app_id=app.id, user_id=user_id, provisioned_at=wanted[user_id]))
        if backfill:
            objs = (await self.db.execute(
                select(AppUser).where(AppUser.app_id == app.id, AppUser.user_id.in_(backfill)))).scalars().all()
            for obj in objs:
                obj.provisioned_at = wanted[obj.user_id]
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
