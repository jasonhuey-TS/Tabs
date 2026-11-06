"""
ReclamationService - finds licenses nobody is using and runs reclamation workflows.

Inputs
    app_users.last_login_at   latest sign-in per person per app (Okta sign-in activity connector,
                              plus any vendor connector). Okta keeps 90 days of history.
    app_users.provisioned_at  when the person was assigned (captured by the Okta sync); people
                              assigned more recently than the inactivity window are never flagged.
    licenses                  annual cost and seats per app, used to estimate savings.

Safety rules
    * Nothing is flagged until the Okta sign-in activity connector has synced at least once -
      otherwise every assignment would look inactive.
    * Apps where NOBODY has a recorded sign-in are treated as "not tracked through Okta" and
      reported separately instead of flagging everyone.
    * Workflows never remove access. They queue items for review; once IT removes access in Okta,
      the next sync detects it and marks the item reclaimed.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.encryption import decrypt, encrypt
from app.models import App, AppUser, License, User
from app.models.connector_config import ConnectorConfig
from app.models.reclamation import ReclamationItem, ReclamationSetting, ReclamationWorkflow
from app.services import slack_outreach as so

ACTIVE_STATUSES = ("open", "approved")
DECIDABLE = ("open", "approved", "kept", "dismissed")
ALL_STATUSES = ("open", "approved", "reclaimed", "kept", "dismissed", "closed")
KEEP_SNOOZE_DAYS = 90
MAX_NEW_ITEMS_PER_RUN = 5000
MAX_WEBHOOK_ITEMS = 200
DEFAULT_ASKS_PER_RUN = 25                    # Slack DMs sent per workflow run (the rest are asked on later runs)
MAX_ASKS_PER_RUN = 200
MAX_MANUAL_ASKS = 50                         # DMs sent from one click in the review queue
SEND_DELAY = 0.4                             # seconds between Slack calls, to stay well inside Slack's rate limits
MIN_DAYS, MAX_DAYS = 14, 90                 # Okta keeps 90 days of sign-in history

# License labels that mean "no paid seat", so reclaiming them saves nothing.
NO_COST_LABELS = ("basic", "unassigned", "none", "unlicensed", "inactive", "deactivated",
                  "disabled", "suspended", "archived")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


_BASE_URL = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d{1,5})?$")


def normalize_base_url(url):
    """The site's public address (scheme + host, no path), or None if it doesn't look right."""
    cleaned = (url or "").strip().rstrip("/")
    return cleaned if _BASE_URL.match(cleaned) else None


def parse_uuid(value):
    """UUID or None - never raises on bad input."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


# ------------------------------------------------------------------ pure helpers (unit-tested)

def per_seat_annual_cents(total_cost_cents, seats):
    """Annual cost of one seat from an app's license totals, or None if it can't be known."""
    if not total_cost_cents or not seats or seats <= 0:
        return None
    return int(round(total_cost_cents / seats))


def days_inactive(now, last_login_at, provisioned_at=None):
    """Whole days since the last sign-in; if there is none, days since assignment (or None)."""
    last = _aware(last_login_at)
    if last is not None:
        return max(0, (now - last).days)
    prov = _aware(provisioned_at)
    if prov is not None:
        return max(0, (now - prov).days)
    return None


def seat_savings_cents(role_label, per_seat_cents):
    """Estimated annual saving from reclaiming one assignment (0 for free/unpaid seats)."""
    if per_seat_cents is None:
        return None
    if (role_label or "").strip().lower() in NO_COST_LABELS:
        return 0
    return per_seat_cents


def plan_run(candidates, existing, gone_keys, now, max_new=MAX_NEW_ITEMS_PER_RUN):
    """Decide what a workflow run does, without touching the database.

    candidates : list of dicts (app_id, user_id, days_inactive, last_login_at, savings), best first
    existing   : {(app_id, user_id): {"id", "status", "snooze_until"}} for this workflow
    gone_keys  : keys of existing items whose assignment no longer exists in Okta
    """
    cand_keys = {(c["app_id"], c["user_id"]) for c in candidates}
    create, update_, reopen, truncated = [], [], [], 0

    for c in candidates:
        key = (c["app_id"], c["user_id"])
        item = existing.get(key)
        fields = {"days_inactive": c["days_inactive"], "last_login_at": c["last_login_at"],
                  "est_annual_savings_cents": c["savings"]}
        if item is None:
            if len(create) < max_new:
                create.append({"app_id": c["app_id"], "user_id": c["user_id"], **fields, "savings": c["savings"]})
            else:
                truncated += 1
        elif item["status"] in ACTIVE_STATUSES:
            update_.append((item["id"], fields))
        elif item["status"] == "kept":
            snooze = _aware(item.get("snooze_until"))
            if snooze is None or snooze <= now:
                reopen.append((item["id"], fields))
        # dismissed / reclaimed / closed items are left alone

    close = []
    for key, item in existing.items():
        if key in cand_keys or item["status"] not in ACTIVE_STATUSES:
            continue
        if key in gone_keys:
            if item["status"] == "approved":
                close.append((item["id"], "reclaimed", "Access removed - assignment no longer exists in Okta."))
            else:
                close.append((item["id"], "closed", "The assignment no longer exists in Okta."))
        else:
            close.append((item["id"], "closed", "Active again, or no longer matches this workflow."))
    return {"create": create, "update": update_, "reopen": reopen, "close": close, "truncated": truncated}


def action_fields(action, now):
    """Column updates for a review decision, or None if the action is unknown."""
    if action == "approve":
        return {"status": "approved", "decided_at": now, "snooze_until": None}
    if action == "keep":
        return {"status": "kept", "decided_at": now, "snooze_until": now + timedelta(days=KEEP_SNOOZE_DAYS)}
    if action == "dismiss":
        return {"status": "dismissed", "decided_at": now, "snooze_until": None}
    if action == "reopen":
        return {"status": "open", "decided_at": None, "snooze_until": None}
    return None


def to_csv(rows, columns):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([label for _key, label in columns])
    for row in rows:
        writer.writerow([row.get(key, "") if row.get(key) is not None else "" for key, _label in columns])
    return out.getvalue()


# ------------------------------------------------------------------ service

class ReclamationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------------- readiness & shared queries

    async def readiness(self) -> dict:
        row = (await self.db.execute(
            select(ConnectorConfig).where(ConnectorConfig.key == "okta_activity"))).scalar_one_or_none()
        last = row.last_sync_at if row else None
        return {"ready": last is not None, "last_sync_at": _iso(last),
                "message": None if last else
                "Sign-in history isn't available yet. Open Integration Library > Okta sign-in activity and run a sync."}

    @staticmethod
    def _tracked_apps():
        """Apps where at least one assignee has a recorded sign-in."""
        return select(AppUser.app_id).group_by(AppUser.app_id).having(func.count(AppUser.last_login_at) > 0)

    @staticmethod
    def _inactive_conditions(cutoff):
        inactive = or_(AppUser.last_login_at.is_(None), AppUser.last_login_at < cutoff)
        aged = or_(AppUser.provisioned_at.is_(None), AppUser.provisioned_at <= cutoff)
        return inactive, aged

    async def seat_costs(self) -> dict:
        rows = await self.db.execute(
            select(License.app_id, func.sum(License.total_annual_cost_cents), func.sum(License.seats_purchased))
            .group_by(License.app_id))
        costs = {}
        for app_id, total, seats in rows.all():
            per_seat = per_seat_annual_cents(total, seats)
            if per_seat is not None:
                costs[app_id] = per_seat
        return costs

    # ---------------------------------------------------------------- analytics

    async def overview(self, days: int) -> dict:
        ready = await self.readiness()
        base = {"days": days, "coverage": ready, "ready": ready["ready"]}
        if not ready["ready"]:
            return {**base, "kpis": None, "by_app": [], "untracked_apps": [], "top_people": [], "buckets": []}

        now = _now()
        cutoff = now - timedelta(days=days)
        inactive, aged = self._inactive_conditions(cutoff)
        flagged = and_(inactive, aged)
        paid = or_(AppUser.role_in_app.is_(None), func.lower(AppUser.role_in_app).not_in(NO_COST_LABELS))

        rows = (await self.db.execute(
            select(AppUser.app_id, App.name, func.count(AppUser.id),
                   func.sum(case((flagged, 1), else_=0)),
                   func.sum(case((and_(flagged, paid), 1), else_=0)),
                   func.count(AppUser.last_login_at))
            .select_from(AppUser)
            .join(App, App.id == AppUser.app_id)
            .group_by(AppUser.app_id, App.name))).all()

        costs = await self.seat_costs()
        by_app, untracked = [], []
        assigned_total = inactive_total = 0
        savings_total, apps_missing_cost = 0, 0
        for app_id, name, assigned, flagged_n, flagged_paid, with_login in rows:
            assigned, flagged_n, flagged_paid = int(assigned or 0), int(flagged_n or 0), int(flagged_paid or 0)
            if int(with_login or 0) == 0:
                untracked.append({"app_id": str(app_id), "name": name, "assigned": assigned})
                continue
            per_seat = costs.get(app_id)
            savings = flagged_paid * per_seat if per_seat is not None else None
            assigned_total += assigned
            inactive_total += flagged_n
            if savings is not None:
                savings_total += savings
            elif flagged_n:
                apps_missing_cost += 1
            if flagged_n:
                by_app.append({"app_id": str(app_id), "name": name, "assigned": assigned, "inactive": flagged_n,
                               "inactive_pct": round(100.0 * flagged_n / assigned, 1) if assigned else 0.0,
                               "est_annual_savings_cents": savings, "cost_known": per_seat is not None})
        by_app.sort(key=lambda r: (-(r["est_annual_savings_cents"] or 0), -r["inactive"], r["name"]))
        untracked.sort(key=lambda r: -r["assigned"])

        tracked = self._tracked_apps()
        edges = [now - timedelta(days=d) for d in (7, 30, 60)]
        b = (await self.db.execute(
            select(func.sum(case((AppUser.last_login_at >= edges[0], 1), else_=0)),
                   func.sum(case((and_(AppUser.last_login_at < edges[0], AppUser.last_login_at >= edges[1]), 1), else_=0)),
                   func.sum(case((and_(AppUser.last_login_at < edges[1], AppUser.last_login_at >= edges[2]), 1), else_=0)),
                   func.sum(case((AppUser.last_login_at < edges[2], 1), else_=0)),
                   func.sum(case((AppUser.last_login_at.is_(None), 1), else_=0)))
            .where(AppUser.app_id.in_(tracked)))).one()
        labels = ["Last 7 days", "8-30 days", "31-60 days", "61-90 days", "No sign-in on record"]
        buckets = [{"label": l, "count": int(v or 0)} for l, v in zip(labels, b)]

        people = (await self.db.execute(
            select(User.email, User.full_name, func.count(AppUser.id))
            .select_from(User)
            .join(AppUser, AppUser.user_id == User.id)
            .where(flagged, AppUser.app_id.in_(tracked))
            .group_by(User.id, User.email, User.full_name)
            .order_by(func.count(AppUser.id).desc(), User.email).limit(10))).all()

        return {**base,
                "kpis": {"assigned": assigned_total, "inactive": inactive_total,
                         "inactive_pct": round(100.0 * inactive_total / assigned_total, 1) if assigned_total else 0.0,
                         "est_annual_savings_cents": savings_total, "apps_missing_cost": apps_missing_cost,
                         "apps_with_opportunities": len(by_app)},
                "by_app": by_app[:200], "untracked_apps": untracked[:50], "buckets": buckets,
                "top_people": [{"email": e, "name": n, "idle_apps": int(c)} for e, n, c in people]}

    def _inactive_query(self, days, app_id, include_untracked):
        cutoff = _now() - timedelta(days=days)
        inactive, aged = self._inactive_conditions(cutoff)
        conds = [inactive, aged]
        if not include_untracked:
            conds.append(AppUser.app_id.in_(self._tracked_apps()))
        if app_id:
            conds.append(AppUser.app_id == app_id)
        return conds

    async def inactive(self, days, app_id=None, include_untracked=False, limit=100, offset=0) -> dict:
        ready = await self.readiness()
        if not ready["ready"]:
            return {"ready": False, "total": 0, "rows": []}
        conds = self._inactive_query(days, parse_uuid(app_id) if app_id else None, include_untracked)
        total = (await self.db.execute(select(func.count(AppUser.id)).where(*conds))).scalar_one()
        rows = (await self.db.execute(
            select(App.id, App.name, User.email, User.full_name, AppUser.last_login_at,
                   AppUser.provisioned_at, AppUser.role_in_app)
            .select_from(AppUser)
            .join(App, App.id == AppUser.app_id).join(User, User.id == AppUser.user_id)
            .where(*conds)
            .order_by(AppUser.last_login_at.asc().nullsfirst(), User.email)
            .limit(limit).offset(offset))).all()
        costs, now = await self.seat_costs(), _now()
        out = []
        for app_pk, app_name, email, name, last, prov, label in rows:
            out.append({"app_id": str(app_pk), "app": app_name, "email": email, "name": name,
                        "last_active": _iso(last), "days_inactive": days_inactive(now, last, prov),
                        "license": label,
                        "est_annual_savings_cents": seat_savings_cents(label, costs.get(app_pk))})
        return {"ready": True, "total": int(total or 0), "rows": out}

    async def inactive_csv(self, days, app_id=None, include_untracked=False) -> str:
        data = await self.inactive(days, app_id, include_untracked, limit=50000, offset=0)
        rows = [{**r, "est_annual_savings": (r["est_annual_savings_cents"] or 0) / 100.0
                 if r["est_annual_savings_cents"] is not None else ""} for r in data["rows"]]
        return to_csv(rows, [("app", "App"), ("name", "Person"), ("email", "Email"), ("license", "License"),
                             ("last_active", "Last sign-in"), ("days_inactive", "Days inactive"),
                             ("est_annual_savings", "Est. annual savings (USD)")])

    # ---------------------------------------------------------------- workflows

    def _workflow_dict(self, wf, counts, app_names) -> dict:
        return {"id": str(wf.id), "name": wf.name, "is_enabled": wf.is_enabled,
                "app_id": str(wf.app_id) if wf.app_id else None,
                "app_name": app_names.get(wf.app_id) if wf.app_id else "All apps",
                "inactivity_days": wf.inactivity_days, "min_savings_usd": (wf.min_savings_cents or 0) / 100.0,
                "notify_slack": bool(wf.notify_slack), "has_webhook": bool(wf.webhook_url_encrypted),
                "auto_run": bool(wf.auto_run), "ask_users_slack": bool(wf.ask_users_slack),
                "ask_users_per_run": wf.ask_users_per_run or DEFAULT_ASKS_PER_RUN, "last_run_at": _iso(wf.last_run_at),
                "last_run_summary": wf.last_run_summary or {}, "counts": counts}

    async def list_workflows(self) -> list:
        workflows = (await self.db.execute(
            select(ReclamationWorkflow).order_by(ReclamationWorkflow.created_at))).scalars().all()
        counts = {}
        for wf_id, status, n in (await self.db.execute(
                select(ReclamationItem.workflow_id, ReclamationItem.status, func.count(ReclamationItem.id))
                .group_by(ReclamationItem.workflow_id, ReclamationItem.status))).all():
            counts.setdefault(wf_id, {})[status] = int(n)
        app_ids = [w.app_id for w in workflows if w.app_id]
        names = {}
        if app_ids:
            names = {i: n for i, n in (await self.db.execute(select(App.id, App.name).where(App.id.in_(app_ids)))).all()}
        return [self._workflow_dict(w, counts.get(w.id, {}), names) for w in workflows]

    async def save_workflow(self, payload: dict, wf_id: str | None = None):
        """Create or update. Returns (ok, message, workflow_id)."""
        name = (payload.get("name") or "").strip()
        if not name or len(name) > 200:
            return False, "Give the workflow a name (up to 200 characters).", None
        try:
            days = int(payload.get("inactivity_days", 60))
        except (TypeError, ValueError):
            return False, "Inactivity days must be a number.", None
        if not MIN_DAYS <= days <= MAX_DAYS:
            return False, f"Inactivity must be between {MIN_DAYS} and {MAX_DAYS} days (Okta keeps 90 days of sign-ins).", None
        try:
            min_cents = int(round(float(payload.get("min_savings_usd") or 0) * 100))
        except (TypeError, ValueError):
            return False, "Minimum savings must be a number.", None
        if min_cents < 0:
            return False, "Minimum savings can't be negative.", None

        webhook = (payload.get("webhook_url") or "").strip()
        if webhook and not webhook.lower().startswith("https://"):
            return False, "The webhook URL must start with https://", None

        ask = bool(payload.get("ask_users_slack"))
        raw_per_run = payload.get("ask_users_per_run")
        try:
            per_run = DEFAULT_ASKS_PER_RUN if raw_per_run in (None, "") else int(raw_per_run)
        except (TypeError, ValueError):
            return False, "'People to ask per run' must be a number.", None
        if not 1 <= per_run <= MAX_ASKS_PER_RUN:
            return False, f"'People to ask per run' must be between 1 and {MAX_ASKS_PER_RUN}.", None
        base_raw = (payload.get("public_base_url") or "").strip()
        base = normalize_base_url(base_raw) if base_raw else None
        if base_raw and base is None:
            return False, "The site address couldn't be read. Open the app from its normal web address and try again.", None
        if ask and not base and not await self.public_base_url():
            return False, "Open the app from its normal web address to turn on Slack questions - that address is used in the buttons.", None

        app_uuid = None
        if payload.get("app_id"):
            try:
                app_uuid = uuid.UUID(str(payload["app_id"]))
            except ValueError:
                return False, "That app isn't valid - pick one from the list.", None
            if (await self.db.execute(select(App.id).where(App.id == app_uuid))).scalar_one_or_none() is None:
                return False, "That app no longer exists - pick another.", None

        wf = None
        if wf_id:
            wf_uuid = parse_uuid(wf_id)
            wf = None if wf_uuid is None else (await self.db.execute(
                select(ReclamationWorkflow).where(ReclamationWorkflow.id == wf_uuid))).scalar_one_or_none()
            if wf is None:
                return False, "That workflow no longer exists.", None
        else:
            wf = ReclamationWorkflow()
            self.db.add(wf)

        wf.name, wf.app_id, wf.inactivity_days, wf.min_savings_cents = name, app_uuid, days, min_cents
        wf.notify_slack = bool(payload.get("notify_slack"))
        wf.auto_run = bool(payload.get("auto_run"))
        wf.ask_users_slack, wf.ask_users_per_run = ask, per_run
        wf.is_enabled = bool(payload.get("is_enabled", True))
        if payload.get("clear_webhook"):
            wf.webhook_url_encrypted = None
        elif webhook:
            wf.webhook_url_encrypted = encrypt(webhook)
        await self.db.flush()
        new_id = str(wf.id)
        if base:
            await self.set_public_base_url(base)
        await self.db.commit()
        return True, "Saved.", new_id

    async def set_enabled(self, wf_id: str, enabled: bool) -> bool:
        wf_uuid = parse_uuid(wf_id)
        if wf_uuid is None:
            return False
        await self.db.execute(update(ReclamationWorkflow)
                              .where(ReclamationWorkflow.id == wf_uuid).values(is_enabled=enabled))
        await self.db.commit()
        return True

    async def delete_workflow(self, wf_id: str) -> bool:
        wf_uuid = parse_uuid(wf_id)
        if wf_uuid is None:
            return False
        await self.db.execute(delete(ReclamationWorkflow).where(ReclamationWorkflow.id == wf_uuid))
        await self.db.commit()
        return True

    # ---------------------------------------------------------------- running a workflow

    async def _candidates(self, wf, now) -> list:
        cutoff = now - timedelta(days=wf.inactivity_days)
        inactive, aged = self._inactive_conditions(cutoff)
        conds = [inactive, aged, AppUser.app_id.in_(self._tracked_apps())]
        if wf.app_id:
            conds.append(AppUser.app_id == wf.app_id)
        rows = (await self.db.execute(
            select(AppUser.app_id, AppUser.user_id, AppUser.last_login_at, AppUser.provisioned_at,
                   AppUser.role_in_app).where(*conds))).all()
        costs = await self.seat_costs()
        out = []
        for app_pk, user_pk, last, prov, label in rows:
            savings = seat_savings_cents(label, costs.get(app_pk))
            if wf.min_savings_cents and (savings is None or savings < wf.min_savings_cents):
                continue
            out.append({"app_id": app_pk, "user_id": user_pk, "days_inactive": days_inactive(now, last, prov),
                        "last_login_at": last, "savings": savings})
        out.sort(key=lambda c: (-(c["savings"] or 0), -(c["days_inactive"] if c["days_inactive"] is not None else 9999)))
        return out

    async def _existing_items(self, wf_id) -> dict:
        rows = (await self.db.execute(
            select(ReclamationItem.id, ReclamationItem.app_id, ReclamationItem.user_id,
                   ReclamationItem.status, ReclamationItem.snooze_until)
            .where(ReclamationItem.workflow_id == wf_id))).all()
        return {(a, u): {"id": i, "status": s, "snooze_until": z} for i, a, u, s, z in rows}

    async def _still_assigned(self, keys) -> set:
        by_app = {}
        for app_pk, user_pk in keys:
            by_app.setdefault(app_pk, []).append(user_pk)
        present = set()
        for app_pk, users in by_app.items():
            rows = await self.db.execute(
                select(AppUser.user_id).where(AppUser.app_id == app_pk, AppUser.user_id.in_(users)))
            present |= {(app_pk, u) for (u,) in rows.all()}
        return present

    async def run_workflow(self, wf_id: str, trigger: str = "manual") -> dict:
        wf_uuid = parse_uuid(wf_id)
        wf = None if wf_uuid is None else (await self.db.execute(
            select(ReclamationWorkflow).where(ReclamationWorkflow.id == wf_uuid))).scalar_one_or_none()
        if wf is None:
            return {"ok": False, "message": "That workflow no longer exists."}
        ready = await self.readiness()
        if not ready["ready"]:
            return {"ok": False, "message": ready["message"]}
        if wf.app_id and (await self.db.execute(select(App.id).where(App.id == wf.app_id))).scalar_one_or_none() is None:
            return {"ok": False, "message": "The app this workflow targets no longer exists."}

        now = _now()
        wf_pk, name, days = wf.id, wf.name, wf.inactivity_days
        slack, webhook_url = wf.notify_slack, (decrypt(wf.webhook_url_encrypted) if wf.webhook_url_encrypted else None)
        ask_slack, ask_limit = bool(wf.ask_users_slack), int(wf.ask_users_per_run or DEFAULT_ASKS_PER_RUN)

        candidates = await self._candidates(wf, now)
        existing = await self._existing_items(wf_pk)
        cand_keys = {(c["app_id"], c["user_id"]) for c in candidates}
        absent = {k for k, it in existing.items() if it["status"] in ACTIVE_STATUSES and k not in cand_keys}
        gone = absent - (await self._still_assigned(absent)) if absent else set()
        plan = plan_run(candidates, existing, gone, now)

        new_rows = []
        for c in plan["create"]:
            item = ReclamationItem(workflow_id=wf_pk, app_id=c["app_id"], user_id=c["user_id"], status="open",
                                   days_inactive=c["days_inactive"], last_login_at=c["last_login_at"],
                                   est_annual_savings_cents=c["est_annual_savings_cents"])
            self.db.add(item)
            new_rows.append(c)
        for item_id, fields in plan["update"]:
            await self.db.execute(update(ReclamationItem).where(ReclamationItem.id == item_id).values(**fields))
        reopened = [i for i, _f in plan["reopen"]]
        for item_id, fields in plan["reopen"]:
            await self.db.execute(update(ReclamationItem).where(ReclamationItem.id == item_id)
                                  .values(status="open", snooze_until=None, asked_at=None, **fields))
        reclaimed = 0
        for item_id, status, note in plan["close"]:
            reclaimed += 1 if status == "reclaimed" else 0
            await self.db.execute(update(ReclamationItem).where(ReclamationItem.id == item_id)
                                  .values(status=status, note=note, decided_at=now))
        await self.db.flush()

        opened = len(new_rows) + len(reopened)
        potential = sum(c["savings"] or 0 for c in candidates)
        summary = {"trigger": trigger, "ran_at": now.isoformat(), "candidates": len(candidates),
                   "new": len(new_rows), "reopened": len(reopened), "updated": len(plan["update"]),
                   "closed": len(plan["close"]) - reclaimed, "reclaimed": reclaimed,
                   "truncated": plan["truncated"], "est_annual_savings_cents": potential, "notifications": {}}
        summary["message"] = (f"{len(candidates):,} assignments inactive for {days}+ days: "
                              f"{len(new_rows):,} new, {len(reopened):,} reopened, {reclaimed:,} confirmed reclaimed."
                              + (f" {plan['truncated']:,} more weren't queued (cap of {MAX_NEW_ITEMS_PER_RUN:,} per run)."
                                 if plan["truncated"] else ""))

        if opened and (slack or webhook_url):
            await self._notify(name, days, new_rows, summary, slack, webhook_url)

        if ask_slack:
            asked = await self._ask_pending(wf_pk, ask_limit)
            summary["outreach"] = {k: asked[k] for k in ("sent", "not_in_slack", "failed")}
            if asked["ok"]:
                summary["message"] += f" {asked['message']}."
            else:
                summary["outreach"]["error"] = asked["message"]
                summary["message"] += f" Slack questions weren't sent: {asked['message']}"

        await self.db.execute(update(ReclamationWorkflow).where(ReclamationWorkflow.id == wf_pk)
                              .values(last_run_at=now, last_run_summary=summary))
        await self.db.commit()
        return {"ok": True, "message": summary["message"], "summary": summary}

    def _http_client(self):
        return httpx.AsyncClient(timeout=15.0)

    async def _notify(self, name, days, new_rows, summary, slack, webhook_url) -> None:
        """Best-effort: a failed notification never fails the run."""
        notes = summary["notifications"]
        savings = sum(c["savings"] or 0 for c in new_rows)
        slack_url = (getattr(app_settings, "SLACK_WEBHOOK_URL", "") or "").strip()
        async with self._http_client() as client:
            if slack:
                if not slack_url:
                    notes["slack"] = "skipped: SLACK_WEBHOOK_URL isn't configured"
                else:
                    text = (f":broom: Reclamation workflow *{name}* found {summary['new'] + summary['reopened']:,} "
                            f"new candidates inactive for {days}+ days (est. ${savings / 100:,.0f}/yr). "
                            "Review them in Tab > Reclamation.")
                    try:
                        resp = await client.post(slack_url, json={"text": text})
                        notes["slack"] = "sent" if resp.status_code < 300 else f"failed: HTTP {resp.status_code}"
                    except Exception as exc:
                        notes["slack"] = f"failed: {type(exc).__name__}"
            if webhook_url:
                payload = {"event": "reclamation.candidates", "workflow": name, "inactivity_days": days,
                           "generated_at": _now().isoformat(), "count": len(new_rows),
                           "items": await self._webhook_items(new_rows[:MAX_WEBHOOK_ITEMS])}
                try:
                    resp = await client.post(webhook_url, json=payload)
                    notes["webhook"] = "sent" if resp.status_code < 300 else f"failed: HTTP {resp.status_code}"
                except Exception as exc:
                    notes["webhook"] = f"failed: {type(exc).__name__}"

    async def _webhook_items(self, rows) -> list:
        if not rows:
            return []
        app_ids = {r["app_id"] for r in rows}
        user_ids = {r["user_id"] for r in rows}
        apps = {i: n for i, n in (await self.db.execute(select(App.id, App.name).where(App.id.in_(app_ids)))).all()}
        users = {i: (e, n) for i, e, n in (await self.db.execute(
            select(User.id, User.email, User.full_name).where(User.id.in_(user_ids)))).all()}
        return [{"app": apps.get(r["app_id"]), "user_email": users.get(r["user_id"], ("", ""))[0],
                 "user_name": users.get(r["user_id"], ("", ""))[1], "days_inactive": r["days_inactive"],
                 "last_sign_in": _iso(r["last_login_at"]),
                 "est_annual_savings_usd": None if r["savings"] is None else r["savings"] / 100.0} for r in rows]

    async def run_all_enabled(self) -> dict:
        """Scheduler entry point: run every enabled workflow marked auto-run."""
        results = {}
        for wf_id, name in (await self.db.execute(
                select(ReclamationWorkflow.id, ReclamationWorkflow.name)
                .where(ReclamationWorkflow.is_enabled.is_(True), ReclamationWorkflow.auto_run.is_(True)))).all():
            try:
                results[name] = (await self.run_workflow(str(wf_id), trigger="schedule")).get("message")
            except Exception as exc:
                await self.db.rollback()
                results[name] = f"error: {exc}"
        return results

    # ---------------------------------------------------------------- asking people in Slack

    async def public_base_url(self):
        row = (await self.db.execute(
            select(ReclamationSetting).where(ReclamationSetting.key == "public_base_url"))).scalar_one_or_none()
        return row.value if row is not None and row.value else None

    async def set_public_base_url(self, url: str) -> None:
        row = (await self.db.execute(
            select(ReclamationSetting).where(ReclamationSetting.key == "public_base_url"))).scalar_one_or_none()
        if row is None:
            self.db.add(ReclamationSetting(key="public_base_url", value=url))
        else:
            row.value = url

    async def _slack_token(self):
        row = (await self.db.execute(select(ConnectorConfig).where(ConnectorConfig.key == "slack"))).scalar_one_or_none()
        if row is None or not row.config_encrypted:
            return None
        try:
            return (json.loads(decrypt(row.config_encrypted)) or {}).get("bot_token") or None
        except Exception:
            return None

    async def _ask_rows(self, *conds, limit=None) -> list:
        stmt = (select(ReclamationItem.id, ReclamationItem.days_inactive, ReclamationItem.last_login_at,
                       App.name, User.email, User.full_name)
                .select_from(ReclamationItem)
                .join(App, App.id == ReclamationItem.app_id)
                .join(User, User.id == ReclamationItem.user_id)
                .where(*conds)
                .order_by(ReclamationItem.est_annual_savings_cents.desc().nullslast(), User.email))
        if limit:
            stmt = stmt.limit(limit)
        rows = (await self.db.execute(stmt)).all()
        return [{"item_id": str(i), "days_inactive": d, "last_login_at": last, "app_name": a, "email": e, "name": n}
                for i, d, last, a, e, n in rows]

    async def _send_asks(self, rows) -> dict:
        """DM each person and mark them asked. Doesn't commit - the caller does."""
        counts = {"sent": 0, "not_in_slack": 0, "failed": 0}
        if not rows:
            return {"ok": True, **counts, "message": "No one to ask"}
        secret = getattr(app_settings, "SECRET_KEY", "")
        if not so.secret_is_safe(secret):
            return {"ok": False, **counts, "message": "SECRET_KEY is still the default value, so the Slack buttons can't be "
                    "signed safely. Set a private SECRET_KEY in your deployment settings first."}
        base = await self.public_base_url()
        if not base:
            return {"ok": False, **counts, "message": "Save a workflow with 'Ask people in Slack' turned on once, from your "
                    "browser - that records the web address used in the buttons."}
        bot_token = await self._slack_token()
        if not bot_token:
            return {"ok": False, **counts, "message": "Connect Slack in the Integration Library first "
                    "(the bot also needs the chat:write scope)."}

        dm, now, asked_ids, fatal = so.SlackDM(bot_token), _now(), [], None
        async with self._http_client() as client:
            for r in rows:
                user_id, err = await dm.user_id(client, r["email"])
                if err == "users_not_found":
                    counts["not_in_slack"] += 1
                    continue
                if err:
                    if err in so.FATAL_ERRORS:
                        fatal = err
                        break
                    counts["failed"] += 1
                    continue
                link = f"{base}/api/v1/reclamation/respond?token={so.make_token(secret, r['item_id'], now)}"
                text, blocks = so.build_message(so.first_name(r["name"], r["email"]), r["app_name"], r["days_inactive"],
                                                r["last_login_at"], f"{link}&answer=keep", f"{link}&answer=release")
                delivered, err = await dm.send(client, user_id, text, blocks)
                if delivered:
                    asked_ids.append(r["item_id"])
                elif err in so.FATAL_ERRORS:
                    fatal = err
                    break
                else:
                    counts["failed"] += 1
                await asyncio.sleep(SEND_DELAY)

        counts["sent"] = len(asked_ids)
        if asked_ids:
            await self.db.execute(update(ReclamationItem)
                                  .where(ReclamationItem.id.in_([parse_uuid(i) for i in asked_ids]))
                                  .values(asked_at=now))
        parts = [f"Asked {counts['sent']} {'person' if counts['sent'] == 1 else 'people'} in Slack"]
        if counts["not_in_slack"]:
            parts.append(f"{counts['not_in_slack']} couldn't be found in Slack by email")
        if counts["failed"]:
            parts.append(f"{counts['failed']} failed")
        message = ", ".join(parts)
        if fatal:
            hint = ("the Slack app needs the chat:write and users:read.email scopes - add them and reinstall the app"
                    if fatal in ("missing_scope", "no_permission") else
                    "Slack rejected the bot token - reconnect Slack in the Integration Library")
            return {"ok": False, **counts, "message": f"{message}. Stopped: {hint}."}
        return {"ok": True, **counts, "message": message}

    async def _ask_pending(self, wf_pk, limit) -> dict:
        """Ask people on this workflow's open items who haven't been asked yet, biggest savings first."""
        rows = await self._ask_rows(ReclamationItem.workflow_id == wf_pk, ReclamationItem.status == "open",
                                    ReclamationItem.asked_at.is_(None), limit=limit)
        return await self._send_asks(rows)

    async def ask_items(self, ids) -> dict:
        """Manual 'Ask in Slack' for selected items that are still waiting for review."""
        uuids = [u for u in (parse_uuid(i) for i in ids) if u]
        if not uuids:
            return {"ok": False, "message": "Select at least one item.", "sent": 0}
        capped = len(uuids) > MAX_MANUAL_ASKS
        rows = await self._ask_rows(ReclamationItem.id.in_(uuids[:MAX_MANUAL_ASKS]), ReclamationItem.status == "open")
        if not rows:
            return {"ok": False, "message": "None of the selected items are waiting for review.", "sent": 0}
        result = await self._send_asks(rows)
        await self.db.commit()
        if capped:
            result["message"] += f" (limited to {MAX_MANUAL_ASKS} at a time)"
        return result

    async def respond(self, token: str, answer: str, confirm: bool = False) -> dict:
        """A person's answer from the Slack buttons. Returns {"state": ..., "app": ...} for the page to show."""
        item_id, err = so.verify_token(getattr(app_settings, "SECRET_KEY", ""), token, _now())
        if err:
            return {"state": err}
        item_uuid = parse_uuid(item_id)
        row = None if item_uuid is None else (await self.db.execute(
            select(ReclamationItem.status, App.name, User.email, User.full_name,
                   ReclamationWorkflow.name, ReclamationWorkflow.webhook_url_encrypted)
            .select_from(ReclamationItem)
            .join(App, App.id == ReclamationItem.app_id)
            .join(User, User.id == ReclamationItem.user_id)
            .join(ReclamationWorkflow, ReclamationWorkflow.id == ReclamationItem.workflow_id)
            .where(ReclamationItem.id == item_uuid))).first()
        if row is None:
            return {"state": "gone"}
        status, app_name, email, full_name, wf_name, hook = row
        if status in ("reclaimed", "closed", "dismissed"):
            return {"state": "inactive", "app": app_name}

        now = _now()
        if answer == "keep":
            if status != "kept":
                await self.db.execute(update(ReclamationItem).where(ReclamationItem.id == item_uuid).values(
                    **action_fields("keep", now), note="Confirmed by the person in Slack"))
                await self.db.commit()
            return {"state": "kept", "app": app_name}
        if answer == "release":
            if status == "approved":
                return {"state": "released", "app": app_name}
            if not confirm:
                return {"state": "confirm_release", "app": app_name}
            await self.db.execute(update(ReclamationItem).where(ReclamationItem.id == item_uuid).values(
                **action_fields("approve", now), note="Released by the person in Slack"))
            await self.db.commit()
            if hook:
                await self._post_released(decrypt(hook), wf_name, app_name, email, full_name, item_id)
            return {"state": "released", "app": app_name}
        return {"state": "invalid"}

    async def _post_released(self, url, workflow, app_name, email, name, item_id) -> None:
        """Tell the workflow's webhook (e.g. Okta Workflows) that a person gave up their license. Best effort."""
        payload = {"event": "reclamation.user_released", "workflow": workflow, "item_id": item_id, "app": app_name,
                   "user_email": email, "user_name": name, "released_at": _now().isoformat()}
        try:
            async with self._http_client() as client:
                await client.post(url, json=payload)
        except Exception:
            pass

    # ---------------------------------------------------------------- review queue

    async def list_items(self, status=None, workflow_id=None, app_id=None, limit=100, offset=0) -> dict:
        conds = []
        if status:
            conds.append(ReclamationItem.status == status)
        if workflow_id and parse_uuid(workflow_id):
            conds.append(ReclamationItem.workflow_id == parse_uuid(workflow_id))
        if app_id and parse_uuid(app_id):
            conds.append(ReclamationItem.app_id == parse_uuid(app_id))
        counts = {s: 0 for s in ALL_STATUSES}
        for s, n in (await self.db.execute(
                select(ReclamationItem.status, func.count(ReclamationItem.id)).group_by(ReclamationItem.status))).all():
            counts[s] = int(n)
        total = (await self.db.execute(select(func.count(ReclamationItem.id)).where(*conds))).scalar_one()
        rows = (await self.db.execute(
            select(ReclamationItem.id, ReclamationItem.status, ReclamationItem.days_inactive,
                   ReclamationItem.last_login_at, ReclamationItem.est_annual_savings_cents,
                   ReclamationItem.snooze_until, ReclamationItem.note, ReclamationItem.updated_at,
                   ReclamationItem.asked_at, App.id, App.name, User.email, User.full_name, ReclamationWorkflow.name)
            .select_from(ReclamationItem)
            .join(App, App.id == ReclamationItem.app_id)
            .join(User, User.id == ReclamationItem.user_id)
            .join(ReclamationWorkflow, ReclamationWorkflow.id == ReclamationItem.workflow_id)
            .where(*conds)
            .order_by(ReclamationItem.est_annual_savings_cents.desc().nullslast(), ReclamationItem.days_inactive.desc().nullslast())
            .limit(limit).offset(offset))).all()
        items = [{"id": str(i), "status": s, "days_inactive": d, "last_active": _iso(l),
                  "est_annual_savings_cents": c, "snooze_until": _iso(z), "note": n, "updated_at": _iso(u),
                  "asked_at": _iso(k), "app_id": str(a), "app": an, "email": e, "name": fn, "workflow": wn}
                 for i, s, d, l, c, z, n, u, k, a, an, e, fn, wn in rows]
        return {"items": items, "total": int(total or 0), "counts": counts}

    async def items_csv(self, status="approved") -> str:
        data = await self.list_items(status=status, limit=50000)
        rows = [{**i, "savings": "" if i["est_annual_savings_cents"] is None else i["est_annual_savings_cents"] / 100.0}
                for i in data["items"]]
        return to_csv(rows, [("app", "App"), ("name", "Person"), ("email", "Email"), ("status", "Status"),
                             ("last_active", "Last sign-in"), ("days_inactive", "Days inactive"),
                             ("savings", "Est. annual savings (USD)"), ("workflow", "Workflow")])

    async def decide(self, ids, action) -> dict:
        fields = action_fields(action, _now())
        if fields is None:
            return {"ok": False, "message": "Unknown action.", "updated": 0}
        try:
            uuids = [uuid.UUID(str(i)) for i in ids][:5000]
        except ValueError:
            return {"ok": False, "message": "One of the selected items isn't valid.", "updated": 0}
        if not uuids:
            return {"ok": False, "message": "Select at least one item.", "updated": 0}
        result = await self.db.execute(
            update(ReclamationItem)
            .where(ReclamationItem.id.in_(uuids), ReclamationItem.status.in_(DECIDABLE))
            .values(**fields))
        await self.db.commit()
        return {"ok": True, "message": f"Updated {result.rowcount or 0} item(s).", "updated": int(result.rowcount or 0)}

    async def stats(self) -> dict:
        counts = {s: 0 for s in ALL_STATUSES}
        savings = {s: 0 for s in ALL_STATUSES}
        for s, n, total in (await self.db.execute(
                select(ReclamationItem.status, func.count(ReclamationItem.id),
                       func.sum(ReclamationItem.est_annual_savings_cents))
                .group_by(ReclamationItem.status))).all():
            counts[s], savings[s] = int(n), int(total or 0)
        return {"counts": counts, "reclaimed_savings_cents": savings["reclaimed"],
                "pipeline_savings_cents": savings["open"] + savings["approved"]}
