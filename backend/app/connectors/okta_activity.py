"""
Okta sign-in activity - last sign-in per person for EVERY app, from Okta's System Log.

Okta records each successful app sign-in as a user.authentication.sso event and keeps
90 days of them. We read those events and record the most recent one per person per app.
Only people already assigned to an app (from the Okta sync) are updated.

Caveats: this shows sign-ins made THROUGH Okta, not activity inside the app, and Okta's
90-day retention means "no sign-in on record" really means "none in the last 90 days".
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .base import ConnectorError, GlobalConnector, Guide, as_aware, parse_dt, send
from .registry import register

PAGE_LIMIT = 1000
FLUSH_EVERY_PAGES = 40          # write progress to the database every ~40,000 events
MAX_BACKFILL_DAYS = 89          # Okta keeps 90 days; asking for more is an error
EVENT_FILTER = 'eventType eq "user.authentication.sso"'


def slug_for(label: str) -> str:
    """The Okta app sync's slug rule, with edge hyphens trimmed so 'Slack ' and 'Slack' match."""
    return (label or "").lower().replace(" ", "-").replace("_", "-").strip("-")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def aggregate_events(events, latest: dict) -> int:
    """Fold successful SSO events into latest[(app_slug, email)] = newest sign-in time."""
    counted = 0
    for e in events:
        if (e.get("outcome") or {}).get("result") != "SUCCESS":
            continue
        email = ((e.get("actor") or {}).get("alternateId") or "").strip().lower()
        when = parse_dt(e.get("published"))
        if "@" not in email or not when:
            continue
        used = False
        for target in e.get("target") or []:
            if target.get("type") != "AppInstance":
                continue
            slug = slug_for(target.get("displayName") or target.get("alternateId") or "")
            if not slug:
                continue
            key = (slug, email)
            if key not in latest or when > latest[key]:
                latest[key] = when
            used = True
        if used:
            counted += 1
    return counted


async def stream_pages(client, url, headers, params):
    """Yield System Log pages, following Okta's rel="next" links until an empty page."""
    next_url, next_params = url, params
    while next_url:
        resp = await send(client, "GET", next_url, params=next_params, headers=headers)
        events = resp.json()
        if not events:
            return
        yield events
        next_url = (resp.links.get("next") or {}).get("url")
        next_params = None


@register
class OktaActivityConnector(GlobalConnector):
    key = "okta_activity"
    name = "Okta sign-in activity"
    vendor = "Okta"
    description = ("Last sign-in for every person on every app, built from Okta's System Log. "
                   "Covers all your apps at once with no per-app setup.")
    color = "#007DC1"
    initials = "Ok"
    provides = ("Last sign-in (all apps)", "Idle users")
    guide = Guide(
        steps=(
            "Nothing to enter - this uses the Okta domain and API token already saved under Settings.",
            "That token's admin role must be able to read the System Log (Read-only administrator or higher).",
            "The first sync backfills up to 90 days of sign-ins and can take a while. Later syncs only read new events.",
            "It reflects sign-ins made through Okta, not activity inside the app. Okta keeps 90 days of history.",
        ),
    )

    async def _creds(self, db):
        from app.models.integration_setting import IntegrationProvider
        from app.services.integration_settings_service import IntegrationSettingsService
        from app.core.config import settings as app_settings
        svc = IntegrationSettingsService(db)
        setting = await svc.get(IntegrationProvider.OKTA)
        domain = (setting.okta_domain if setting else "") or getattr(app_settings, "OKTA_DOMAIN", "") or ""
        token = (svc.get_okta_token(setting) if setting else "") or getattr(app_settings, "OKTA_API_TOKEN", "") or ""
        return domain.replace("https://", "").strip().strip("/"), token.strip()

    async def is_ready(self, db) -> bool:
        try:
            domain, token = await self._creds(db)
        except Exception:
            await db.rollback()
            return False
        return bool(domain and token)

    def _headers(self, token):
        return {"Authorization": f"SSWS {token}", "Accept": "application/json"}

    def _friendly(self, exc: ConnectorError) -> ConnectorError:
        if " 403" in str(exc):
            return ConnectorError("Okta refused to share the System Log (403). The API token's admin role "
                                  "needs permission to view the System Log - e.g. Read-only administrator.")
        return exc

    async def test(self, cfg, db=None) -> str:
        domain, token = await self._creds(db)
        if not domain or not token:
            raise ConnectorError("Save your Okta domain and API token under Settings first.")
        since = iso(datetime.now(timezone.utc) - timedelta(hours=1))
        try:
            async with self.make_client() as client:
                resp = await send(client, "GET", f"https://{domain}/api/v1/logs", headers=self._headers(token),
                                  params={"filter": EVENT_FILTER, "since": since, "limit": 1})
        except ConnectorError as exc:
            raise self._friendly(exc)
        resp.json()
        return "Connected - Okta's System Log is readable"

    async def _apply(self, db, latest: dict) -> dict:
        """Write the newest sign-in per (app, person) onto already-assigned users."""
        from sqlalchemy import select, func
        from app.models import App, AppUser, User

        by_slug = defaultdict(list)
        for app_id, slug in (await db.execute(select(App.id, App.vendor_slug))).all():
            by_slug[slug_for(slug)].append(app_id)

        per_app, unknown_apps = defaultdict(dict), set()
        for (slug, email), when in latest.items():
            ids = by_slug.get(slug)
            if not ids:
                unknown_apps.add(slug)
                continue
            for app_id in ids:
                per_app[app_id][email] = when

        updated = 0
        for app_id, emails in per_app.items():
            rows = (await db.execute(
                select(AppUser, User.email)
                .join(User, User.id == AppUser.user_id)
                .where(AppUser.app_id == app_id, func.lower(User.email).in_(list(emails)))
            )).all()
            for app_user, email in rows:
                when = emails.get((email or "").lower())
                current = as_aware(app_user.last_login_at)
                if when and (current is None or when > current):
                    app_user.last_login_at = when
                    updated += 1
        await db.flush()
        return {"updated": updated, "unknown_apps": unknown_apps}

    async def run(self, db, state, progress):
        domain, token = await self._creds(db)
        if not domain or not token:
            raise ConnectorError("Save your Okta domain and API token under Settings first.")

        state = state or {}
        floor = datetime.now(timezone.utc) - timedelta(days=MAX_BACKFILL_DAYS)
        since = max(parse_dt(state.get("since")) or floor, floor)
        params = {"filter": EVENT_FILTER, "since": iso(since), "limit": PAGE_LIMIT, "sortOrder": "ASCENDING"}

        latest, pages, seen, updated, last_published = {}, 0, 0, 0, None
        unknown_apps = set()
        try:
            async with self.make_client() as client:
                async for events in stream_pages(client, f"https://{domain}/api/v1/logs",
                                                 self._headers(token), params):
                    pages += 1
                    seen += aggregate_events(events, latest)
                    last_published = parse_dt(events[-1].get("published")) or last_published
                    if pages % FLUSH_EVERY_PAGES == 0 and last_published:
                        result = await self._apply(db, latest)
                        updated += result["updated"]
                        unknown_apps |= result["unknown_apps"]
                        latest.clear()
                        await progress(f"Processed {seen:,} sign-ins (through {last_published:%b %d})",
                                       {"since": iso(last_published)})
        except ConnectorError as exc:
            raise self._friendly(exc)

        if latest:
            result = await self._apply(db, latest)
            updated += result["updated"]
            unknown_apps |= result["unknown_apps"]

        new_state = {"since": iso(last_published or since)}
        message = (f"Read {seen:,} sign-ins; updated last sign-in on {updated:,} user-app records."
                   if seen else "No new sign-ins since the last sync.")
        summary = {"events": seen, "updated": updated, "apps_not_in_library": len(unknown_apps),
                   "through": iso(last_published) if last_published else None, "message": message}
        return summary, new_state
