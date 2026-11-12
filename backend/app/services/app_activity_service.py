"""Everything the app screen's Users tab shows: each person assigned to an app, their last activity,
and their org details (department, cost center, division), plus where the data comes from."""
from __future__ import annotations

from datetime import datetime, timezone

import json
from datetime import timedelta

from sqlalchemy import func, select

from app.models import App, AppUser, User
from app.models.app_extras import AppSetting, AppUserAttribute, EmployeeRoster, UserActiveDay
from app.models.connector_config import ConnectorConfig
from app.models.reclamation import ReclamationSetting
from app.models.user_profile import UserProfile
from app.services import activity_import as ai
from app.services import payment_import as pi
from app.services.app_events import record_event
from app.services.reclamation_service import days_inactive, parse_uuid
from app.services.user_attributes import infer_fields

MAX_USERS = 5000
MAX_IMPORT_CHARS = 15_000_000
DEFAULT_THRESHOLD = 30
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
        threshold = (await self.db.execute(
            select(AppSetting.activity_threshold_days).where(AppSetting.app_id == app_uuid))).scalar_one_or_none() or DEFAULT_THRESHOLD
        rows = (await self.db.execute(
            select(AppUser.user_id, User.email, User.full_name, User.department, AppUser.last_login_at, AppUser.provisioned_at,
                   AppUser.role_in_app, UserProfile.first_name, UserProfile.last_name, UserProfile.title,
                   UserProfile.department, UserProfile.cost_center, UserProfile.division, UserProfile.organization,
                   UserProfile.employee_type, UserProfile.okta_id, UserProfile.okta_status)
            .select_from(AppUser)
            .join(User, User.id == AppUser.user_id)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(AppUser.app_id == app_uuid)
            .order_by(User.email).limit(MAX_USERS))).all()

        # Days active in the last 90: only meaningful once per-day activity has been recorded for this app.
        has_days = bool((await self.db.execute(
            select(func.count()).select_from(UserActiveDay).where(UserActiveDay.app_id == app_uuid))).scalar_one())
        day_counts = {}
        if has_days:
            window_start = now.date() - timedelta(days=90)
            day_counts = {uid: int(n) for uid, n in (await self.db.execute(
                select(UserActiveDay.user_id, func.count()).where(UserActiveDay.app_id == app_uuid, UserActiveDay.day >= window_start)
                .group_by(UserActiveDay.user_id))).all()}

        roster_loaded = bool((await self.db.execute(select(func.count()).select_from(EmployeeRoster))).scalar_one())
        in_roster = set()
        if roster_loaded and rows:
            in_roster = {e for (e,) in (await self.db.execute(
                select(EmployeeRoster.email).where(EmployeeRoster.email.in_([r[1].lower() for r in rows])))).all()}

        attrs_by_user, attr_source = {}, None
        for uid, source, data in (await self.db.execute(
                select(AppUserAttribute.user_id, AppUserAttribute.source, AppUserAttribute.data).where(AppUserAttribute.app_id == app_uuid))).all():
            attrs_by_user[uid] = data or {}
            attr_source = attr_source or source

        users, counts = [], {b: 0 for b, _ in BUCKETS}
        for (user_id, email, full_name, user_dept, last, prov, license_label, first, last_name, title, dept, cost_center,
             division, org, employee_type, okta_id, okta_status) in rows:
            if not first and not last_name:
                first, last_name = split_name(full_name, email)
            days = days_inactive(now, last)                  # only real activity: no fallback to the assignment date
            counts[activity_bucket(days)] += 1
            users.append({"email": email, "first_name": first, "last_name": last_name, "title": title,
                          "department": dept or user_dept, "cost_center": cost_center, "division": division,
                          "organization": org, "employee_type": employee_type, "license": license_label,
                          "last_activity": _iso(last), "days_since": days, "assigned_on": _iso(prov),
                          "active": days is not None and days <= threshold,
                          "days_active": day_counts.get(user_id, 0) if has_days else None,
                          "external_status": okta_status, "external_user_id": okta_id, "source": "Okta",
                          "in_roster": (email.lower() in in_roster) if roster_loaded else None,
                          "attrs": attrs_by_user.get(user_id) or {}})

        # Do we have Okta profile details (names, cost center, ...) for anyone here? If not, say why.
        profile_people = sum(1 for r in rows if any(v is not None for v in (r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15], r[16])))
        profile_diag = None
        if rows and profile_people == 0:
            raw = (await self.db.execute(select(ReclamationSetting.value).where(ReclamationSetting.key == "okta_profile_diag"))).scalar_one_or_none()
            try:
                profile_diag = json.loads(raw) if raw else None
            except ValueError:
                profile_diag = None

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

        attribute_fields, attribute_label = [], None
        if attrs_by_user:
            attribute_label = f"Direct Integration ({CONNECTOR_NAMES.get(attr_source, attr_source)})"
            declared = []
            try:                                                           # the connector says what each field is; fall back to guessing from the values
                from app.connectors import get as get_connector              # local import: avoids a load-order cycle
                declared = [{"key": f.key, "label": f.label, "type": f.type} for f in get_connector(attr_source).attribute_fields]
            except Exception:
                declared = []
            present = {k for d in attrs_by_user.values() for k in d}
            attribute_fields = [f for f in declared if f["key"] in present] or infer_fields(attrs_by_user.values())

        return {"app": {"id": str(app[0]), "name": app[1]}, "total": len(users), "users": users,
                "attribute_fields": attribute_fields, "attribute_source": attribute_label,
                "buckets": [{"id": b, "label": label, "count": counts[b]} for b, label in BUCKETS],
                "sources": sources, "last_refreshed": _iso(max(refreshed)) if refreshed else None,
                "signal": signal, "activity_threshold_days": threshold, "has_days": has_days, "roster_loaded": roster_loaded,
                "profile_people": profile_people, "profile_diag": profile_diag}

    # ------------------------------------------------------------------ filling in older last-activity dates
    async def _import_plan(self, app_id, text, mapping):
        """(context, None) or (None, error response). Reads only."""
        app_uuid = parse_uuid(app_id)
        if app_uuid is None or (await self.db.execute(select(App.id).where(App.id == app_uuid))).scalar_one_or_none() is None:
            return None, {"error": "That app no longer exists."}
        if len(text or "") > MAX_IMPORT_CHARS:
            return None, {"error": "That file is too large (15 MB maximum)."}
        headers, rows = pi.parse_csv(text)
        if not headers:
            return None, {"error": "That file is empty or isn't a CSV."}
        if not rows:
            return None, {"error": "The file has a header row but no people."}
        chosen = {f: h for f, h in (mapping or {}).items() if f in ("email", "date") and h in headers} if mapping else ai.detect_columns(headers)
        rows_db = (await self.db.execute(
            select(AppUser, User.email).select_from(AppUser).join(User, User.id == AppUser.user_id)
            .where(AppUser.app_id == app_uuid))).all()
        people = {(email or "").strip().lower(): au for au, email in rows_db}
        plan = ai.plan_activity_import(rows, chosen, {e: au.last_login_at for e, au in people.items()}, datetime.now(timezone.utc).date())
        return {"app_uuid": app_uuid, "headers": headers, "rows": rows, "mapping": chosen, "plan": plan, "people": people}, None

    async def import_preview(self, app_id, text, mapping=None) -> dict:
        ctx, error = await self._import_plan(app_id, text, mapping)
        if error:
            return error
        plan = ctx["plan"]
        base = {"headers": ctx["headers"], "mapping": ctx["mapping"], "sample": ctx["rows"][:5], "rows": len(ctx["rows"])}
        if plan["error"]:
            return {**base, "error": plan["error"]}
        updates = plan["updates"]
        return {**base, "error": None, "will_update": len(updates), "filled": sum(1 for u in updates if u["old"] is None),
                "unchanged": plan["unchanged"], "no_date": plan["no_date"], "merged": plan["merged"],
                "not_assigned": {"count": len(plan["not_assigned"]), "sample": [n["email"] for n in plan["not_assigned"][:20]]},
                "invalid": {"count": len(plan["invalid"]), "sample": plan["invalid"][:20]},
                "examples": [{"email": u["email"], "old": _iso(u["old"]), "new": _iso(u["new"])} for u in updates[:10]]}

    async def import_commit(self, app_id, text, mapping=None, file_name="upload.csv") -> dict:
        ctx, error = await self._import_plan(app_id, text, mapping)
        if error:
            return {"ok": False, **error}
        plan = ctx["plan"]
        if plan["error"]:
            return {"ok": False, "error": plan["error"]}
        for u in plan["updates"]:
            ctx["people"][u["email"]].last_login_at = u["new"]
        await self.db.flush()
        filled = sum(1 for u in plan["updates"] if u["old"] is None)
        if plan["updates"]:
            await record_event(self.db, ctx["app_uuid"], "activity_import",
                               f"Imported last-activity dates from {str(file_name)[:80]}: {len(plan['updates']):,} updated ({filled:,} had none before)")
        await self.db.commit()
        return {"ok": True, "error": None, "updated": len(plan["updates"]), "filled": filled, "unchanged": plan["unchanged"],
                "no_date": plan["no_date"], "not_assigned": len(plan["not_assigned"]), "invalid": len(plan["invalid"])}

