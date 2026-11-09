"""Everything the app screen's Users tab shows: each person assigned to an app, their last activity,
and their org details (department, cost center, division), plus where the data comes from."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import App, AppUser, User
from app.models.connector_config import ConnectorConfig
from app.models.user_profile import UserProfile
from app.services.reclamation_service import days_inactive, parse_uuid

MAX_USERS = 5000
BUCKETS = [("d30", "0 - 30 days"), ("d60", "31 - 60 days"), ("d90", "61 - 90 days"),
           ("d91", "91+ days"), ("none", "No activity")]
CONNECTOR_NAMES = {"zoom": "Zoom", "slack": "Slack", "google_workspace": "Google Workspace",
                   "microsoft365": "Microsoft 365", "salesforce": "Salesforce", "claude": "Claude"}


def activity_bucket(days):
    """Which colour band a person falls in, from whole days since their last activity (None = never)."""
    if days is None:
        return "none"
    if days <= 30:
        return "d30"
    if days <= 60:
        return "d60"
    if days <= 90:
        return "d90"
    return "d91"


def split_name(full_name, email):
    """(first, last) from a display name, for people whose Okta profile has no separate names."""
    name = (full_name or "").strip()
    if not name or "@" in name:
        return None, None
    parts = name.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else None)


def _iso(dt):
    return dt.isoformat() if dt else None


class AppActivityService:
    def __init__(self, db):
        self.db = db

    async def get(self, app_id: str):
        """None if the app doesn't exist."""
        app_uuid = parse_uuid(app_id)
        app = None if app_uuid is None else (await self.db.execute(
            select(App.id, App.name).where(App.id == app_uuid))).first()
        if app is None:
            return None

        now = datetime.now(timezone.utc)
        rows = (await self.db.execute(
            select(User.email, User.full_name, User.department, AppUser.last_login_at, AppUser.provisioned_at,
                   AppUser.role_in_app, UserProfile.first_name, UserProfile.last_name, UserProfile.title,
                   UserProfile.department, UserProfile.cost_center, UserProfile.division,
                   UserProfile.organization)
            .select_from(AppUser)
            .join(User, User.id == AppUser.user_id)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(AppUser.app_id == app_uuid)
            .order_by(User.email).limit(MAX_USERS))).all()

        users, counts = [], {b: 0 for b, _ in BUCKETS}
        for (email, full_name, user_dept, last, prov, license_label, first, last_name, title,
             dept, cost_center, division, org) in rows:
            if not first and not last_name:
                first, last_name = split_name(full_name, email)
            days = days_inactive(now, last)                  # only real activity: no fallback to the assignment date
            counts[activity_bucket(days)] += 1
            users.append({"email": email, "first_name": first, "last_name": last_name, "title": title,
                          "department": dept or user_dept, "cost_center": cost_center, "division": division,
                          "organization": org, "license": license_label, "last_activity": _iso(last),
                          "days_since": days, "assigned_on": _iso(prov)})

        sources, refreshed = ["Okta assignments"], []
        for key, target, last_sync in (await self.db.execute(
                select(ConnectorConfig.key, ConnectorConfig.target_app_id, ConnectorConfig.last_sync_at)
                .where(ConnectorConfig.last_sync_at.is_not(None)))).all():
            if key == "okta_activity":
                sources.append("Okta sign-ins")
                refreshed.append(last_sync)
            elif target == app_uuid:
                sources.append(CONNECTOR_NAMES.get(key, key))
                refreshed.append(last_sync)

        from app.services.reclamation_service import ReclamationService     # local import: avoids a load-order cycle
        signal = (await ReclamationService(self.db).counted_apps())["counted"].get(app_uuid) or "okta"

        return {"app": {"id": str(app[0]), "name": app[1]}, "total": len(users), "users": users,
                "buckets": [{"id": b, "label": label, "count": counts[b]} for b, label in BUCKETS],
                "sources": sources, "last_refreshed": _iso(max(refreshed)) if refreshed else None,
                "signal": signal}
