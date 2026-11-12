"""Everything behind the app screen's tabs other than Users: App Info, History, Contracts, Savings, Payments,
Documents, Sentiment and Alerts - plus the activity threshold, notes, saved filters and the HR roster.

What's calculated (Contracts, Savings, Alerts) comes only from data already in the system. What's entered by
hand (Payments, Documents, Sentiment, App Info) is stored as entered and labelled as such in the UI."""
from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update

from app.models import App, AppCategory, AppUser, License
from app.models.app_extras import (AppDocument, AppEvent, AppFeedback, AppPayment, AppSetting, EmployeeRoster,
                                   SavedFilter, UserActiveDay)
from app.models.connector_config import ConnectorConfig
from app.models.contract import Contract
from app.models.reclamation import ReclamationItem
from app.services.app_events import record_event
from app.services.category_import import CATEGORIES, LABELS
from app.services.reclamation_service import ReclamationService, parse_uuid, seat_savings_cents

DEFAULT_THRESHOLD = 30
MIN_THRESHOLD, MAX_THRESHOLD = 7, 365
DOC_TYPES = ("contract", "invoice", "security", "dpa", "other")
BAND_IDS = ("d30", "d60", "d90", "d91", "none")
MAX_ROSTER = 100_000
CONNECTOR_NAMES = {"zoom": "Zoom", "slack": "Slack", "google_workspace": "Google Workspace", "microsoft365": "Microsoft 365",
                   "salesforce": "Salesforce", "claude": "Claude", "okta_activity": "Okta sign-in activity"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}


def _iso(value):
    return value.isoformat() if value else None


def _enum(value):
    return getattr(value, "value", value)


def _usd(cents):
    return f"${(cents or 0) / 100:,.0f}"


def _text(value, limit):
    cleaned = (str(value).strip() if value is not None else "")
    return cleaned[:limit] or None


def parse_roster(text: str) -> list:
    """Unique, lower-cased emails found anywhere in pasted text or a CSV, in first-seen order."""
    seen, out = set(), []
    for match in EMAIL_RE.findall(text or ""):
        email = match.lower()
        if email not in seen:
            seen.add(email)
            out.append(email)
    return out


FILTER_OPS = ("gte", "lte", "eq", "between", "contains", "before", "after", "last_days", "older_days", "blank")
_FILTER_KEY = re.compile(r"^[a-z0-9_]{1,60}$")
MAX_FILTERS = 40


def _scalar(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and abs(value) < 1e12:
        return value
    if isinstance(value, str):
        return value.strip()[:255]
    return None


def clean_filter_config(config) -> dict | None:
    """Keep only the parts of a saved filter the Users tab understands; None if it isn't usable.

    A filter on a field is either a list of ticked values (the original form), or {op, value, value2} for ranges, dates and text.
    Field keys are free-form (the Users tab offers different fields for different apps) but must look like keys."""
    if not isinstance(config, dict):
        return None
    out = {"search": _text(config.get("search"), 100) or "",
           "bands": [b for b in (config.get("bands") or []) if b in BAND_IDS],
           "filters": {}, "sort": None}
    raw = config.get("filters") if isinstance(config.get("filters"), dict) else {}
    for key, spec in list(raw.items())[:MAX_FILTERS * 2]:
        if not isinstance(key, str) or not _FILTER_KEY.match(key) or len(out["filters"]) >= MAX_FILTERS:
            continue
        if isinstance(spec, list):
            values = [str(v)[:255] for v in spec if isinstance(v, str)][:50]
            if values:
                out["filters"][key] = values
        elif isinstance(spec, dict) and spec.get("op") in FILTER_OPS:
            cleaned = {"op": spec["op"]}
            for part in ("value", "value2"):
                if part in spec and _scalar(spec[part]) is not None:
                    cleaned[part] = _scalar(spec[part])
            if cleaned["op"] != "blank" and "value" not in cleaned:
                continue                                     # a range with no number or date can never match anything
            if cleaned["op"] == "between" and "value2" not in cleaned:
                continue
            out["filters"][key] = cleaned
    sort = config.get("sort")
    if isinstance(sort, dict) and isinstance(sort.get("col"), str) and sort.get("dir") in ("asc", "desc"):
        out["sort"] = {"col": sort["col"][:60], "dir": sort["dir"]}
    return out


def rolling_active_counts(rows, start: date, end: date, window: int) -> list:
    """Distinct people active in the `window` days up to and including each day from start to end.

    rows: (user_id, day) pairs. Returns [{"day": iso, "active": n}]. One pass over the data."""
    by_day = defaultdict(list)
    for user_id, day in rows:
        by_day[day].append(user_id)
    inside, series = Counter(), []
    cur = start - timedelta(days=window - 1)
    while cur <= end:
        for user_id in by_day.get(cur, ()):
            inside[user_id] += 1
        for user_id in by_day.get(cur - timedelta(days=window), ()):
            inside[user_id] -= 1
            if inside[user_id] <= 0:
                del inside[user_id]
        if cur >= start:
            series.append({"day": cur.isoformat(), "active": len(inside)})
        cur += timedelta(days=1)
    return series


def build_alerts(ctx: dict) -> list:
    """The app's alerts, from one dict of facts. Each alert: id, severity (high/medium/info), title, detail, tab."""
    today, alerts = ctx["today"], []

    def add(alert_id, severity, title, detail, tab):
        alerts.append({"id": alert_id, "severity": severity, "title": title, "detail": detail, "tab": tab})

    for c in ctx.get("contracts", []):
        if c.get("status") != "active" or not c.get("end_date"):
            continue
        days = (c["end_date"] - today).days
        cancel_by = c.get("cancel_by")
        if days < 0:
            add(f"contract-past-{c['id']}", "medium", "A contract is past its end date",
                f"It ended {-days} day{'s' if days != -1 else ''} ago ({c['end_date']:%b %-d, %Y}) but is still marked active.", "contracts")
        elif days <= 90:
            note = ""
            if c.get("auto_renews"):
                note = (f" It renews automatically unless cancelled by {cancel_by:%b %-d, %Y}." if cancel_by and cancel_by >= today
                        else " It renews automatically and the cancellation window has passed." if cancel_by else " It renews automatically.")
            add(f"contract-ending-{c['id']}", "high" if days <= 30 else "medium",
                f"Contract ends in {days} day{'s' if days != 1 else ''}", f"Ends {c['end_date']:%b %-d, %Y}.{note}", "contracts")

    for lic in ctx.get("licenses", []):
        bought, assigned, util = lic.get("seats_purchased"), lic.get("seats_assigned"), lic.get("utilization_pct")
        if bought and assigned and assigned > bought:
            add("over-assigned", "high", "More people are assigned than seats purchased",
                f"{assigned:,} assigned vs {bought:,} purchased.", "savings")
        elif bought and bought >= 5 and util is not None and float(util) < 50:
            waste = lic.get("waste_cost_cents")
            add("low-utilization", "medium", f"Only {float(util):.0f}% of purchased seats are in use",
                f"About {_usd(waste)} a year goes to unused seats." if waste else f"{bought:,} seats purchased.", "savings")

    assigned, inactive, days = ctx.get("assigned") or 0, ctx.get("inactive"), ctx.get("inactive_days")
    if inactive is not None and assigned >= 5 and inactive / assigned >= 0.2:
        pot = ctx.get("potential_cents")
        add("idle-users", "medium", f"{inactive:,} of {assigned:,} people haven't been active in {days}+ days",
            f"That's {inactive / assigned:.0%} of the people assigned." + (f" Reclaiming them could save about {_usd(pot)} a year." if pot else ""),
            "users")
    if ctx.get("signal") == "okta" and assigned:
        add("unverified-usage", "info", "Usage can't be verified from Okta alone",
            "Only Okta sign-ins are available for this app. Apps that keep people signed in look idle even when used daily, "
            "so connect a usage source before reclaiming licenses.", "users")
    for issue in ctx.get("connector_issues", []):
        add(f"connector-{issue['key']}", "medium", issue["title"], issue["detail"], "users")
    if ctx.get("pending_removals"):
        n = ctx["pending_removals"]
        add("pending-removals", "info", f"{n:,} approved removal{'s' if n != 1 else ''} waiting",
            "These people were approved for reclamation. Remove their access in Okta and the next sync will confirm it.", "savings")
    if not ctx.get("owner"):
        add("no-owner", "info", "No owner assigned", "Add an owner on the App Info tab so renewals and reviews have someone responsible.", "info")
    if ctx.get("is_shadow_it"):
        add("shadow-it", "medium", "Marked as shadow IT", "This app was found in use without going through approved purchasing.", "info")
    if assigned >= 10 and not ctx.get("has_cost"):
        add("no-cost", "info", "No license cost on file", "Savings can't be estimated until the cost is imported on the Licenses page.", "savings")

    alerts.sort(key=lambda a: SEVERITY_ORDER[a["severity"]])
    return alerts


class AppDetailsService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ shared
    async def _app(self, app_id):
        app_uuid = parse_uuid(app_id)
        if app_uuid is None:
            return None, None
        row = (await self.db.execute(
            select(App.id, App.name, App.vendor, App.category, App.status, App.owner_email, App.department, App.website,
                   App.description, App.is_shadow_it, App.first_seen_at, App.discovered_via)
            .where(App.id == app_uuid))).first()
        return app_uuid, row

    async def _threshold(self, app_uuid) -> int:
        value = (await self.db.execute(
            select(AppSetting.activity_threshold_days).where(AppSetting.app_id == app_uuid))).scalar_one_or_none()
        return value or DEFAULT_THRESHOLD

    # ------------------------------------------------------------------ settings, notes, app info
    async def get_settings(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        row = (await self.db.execute(select(AppSetting).where(AppSetting.app_id == app_uuid))).scalar_one_or_none()
        get = lambda attr, fallback: (getattr(row, attr, None) if row is not None else None) or fallback
        return {
            "activity_threshold_days": (row.activity_threshold_days if row is not None and row.activity_threshold_days else DEFAULT_THRESHOLD),
            "notes": (row.notes if row is not None else None) or "",
            "info": {"owner_email": get("owner_email", app[5]), "business_owner": get("business_owner", None),
                     "department": get("department", app[6]), "website": get("website", app[7]),
                     "description": get("description", app[8]), "tags": (row.tags if row is not None else None) or [],
                     "certifications": (row.certifications if row is not None else None) or [],
                     "subcategory": (row.app_subcategory if row is not None else None) or "", "functions": (row.app_functions if row is not None else None) or []},
            "base": {"name": app[1], "vendor": app[2], "category": _enum(app[3]), "status": _enum(app[4]),
                     "is_shadow_it": bool(app[9]), "first_seen_at": _iso(app[10]), "discovered_via": app[11]},
        }

    async def save_settings(self, app_id, payload: dict):
        """Partial update: only the keys present are changed. Returns (ok, message)."""
        app_uuid, app = await self._app(app_id)
        if app is None:
            return False, "That app no longer exists."
        changes = {}
        if "activity_threshold_days" in payload:
            try:
                days = int(payload["activity_threshold_days"])
            except (TypeError, ValueError):
                return False, "The activity threshold must be a number of days."
            if not MIN_THRESHOLD <= days <= MAX_THRESHOLD:
                return False, f"The activity threshold must be between {MIN_THRESHOLD} and {MAX_THRESHOLD} days."
            changes["activity_threshold_days"] = days
        if "notes" in payload:
            changes["notes"] = _text(payload["notes"], 10000)
        for field, limit in (("business_owner", 255), ("department", 255), ("description", 4000)):
            if field in payload:
                changes[field] = _text(payload[field], limit)
        if "owner_email" in payload:
            owner = _text(payload["owner_email"], 255)
            if owner and "@" not in owner:
                return False, "The owner should be an email address."
            changes["owner_email"] = owner
        if "website" in payload:
            site = _text(payload["website"], 512)
            if site and not re.match(r"^https?://", site, re.I):
                return False, "The website must start with http:// or https://"
            changes["website"] = site
        category_change = None
        if "category" in payload:
            category_change = str(payload["category"] or "").strip().lower()
            if category_change not in CATEGORIES:
                return False, "Pick one of the listed categories."
        if "subcategory" in payload:
            changes["app_subcategory"] = _text(payload["subcategory"], 120)
        if "functions" in payload:
            if not isinstance(payload["functions"], list):
                return False, "Functions must be a list."
            seen, fns = set(), []
            for x in payload["functions"][:10]:
                fn = _text(x, 120)
                if fn and fn.lower() not in seen:
                    seen.add(fn.lower()); fns.append(fn)
            changes["app_functions"] = fns
        for field in ("tags", "certifications"):
            if field in payload:
                values = payload[field]
                if not isinstance(values, list):
                    return False, f"{field.capitalize()} must be a list."
                changes[field] = [t for t in (_text(x, 60) for x in values[:30]) if t]

        row = (await self.db.execute(select(AppSetting).where(AppSetting.app_id == app_uuid))).scalar_one_or_none()
        if row is None:
            row = AppSetting(app_id=app_uuid, activity_threshold_days=DEFAULT_THRESHOLD)
            self.db.add(row)
        changed = [k for k, v in changes.items() if getattr(row, k, None) != v]
        for key, value in changes.items():
            setattr(row, key, value)
        if "activity_threshold_days" in changed:
            await record_event(self.db, app_uuid, "settings", f"Activity threshold set to {changes['activity_threshold_days']} days")
        if "notes" in changed:
            await record_event(self.db, app_uuid, "notes", "Notes updated")
        info_changed = [k for k in changed if k not in ("activity_threshold_days", "notes")]
        if info_changed:
            nice = {"app_subcategory": "subcategory", "app_functions": "functions"}
            await record_event(self.db, app_uuid, "app_info", "App info updated: " + ", ".join(nice.get(k, k.replace("_", " ")) for k in info_changed))
        if category_change and category_change != _enum(app[3]):
            await self.db.execute(update(App).where(App.id == app_uuid).values(category=AppCategory(category_change)))
            await record_event(self.db, app_uuid, "app_info", f"Category set to {LABELS[category_change]}")
        await self.db.commit()
        return True, "Saved."

    # ------------------------------------------------------------------ contracts
    async def contracts(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        rows = (await self.db.execute(
            select(Contract.id, Contract.status, Contract.start_date, Contract.end_date, Contract.signed_date,
                   Contract.auto_renews, Contract.cancellation_notice_days, Contract.total_value_cents, Contract.currency,
                   Contract.owner_email, Contract.vendor_contact, Contract.file_name, Contract.notes)
            .where(Contract.app_id == app_uuid).order_by(Contract.end_date.desc().nullslast()))).all()
        today, out = datetime.now(timezone.utc).date(), []
        for cid, status, start, end, signed, auto, notice, value, currency, owner, vendor_contact, file_name, notes in rows:
            cancel_by = end - timedelta(days=notice) if end and notice else None
            out.append({"id": str(cid), "status": _enum(status), "start_date": _iso(start), "end_date": _iso(end),
                        "signed_date": _iso(signed), "auto_renews": bool(auto), "cancellation_notice_days": notice,
                        "cancel_by": _iso(cancel_by), "days_to_end": (end - today).days if end else None,
                        "total_value_cents": value, "currency": currency, "owner_email": owner,
                        "vendor_contact": vendor_contact, "file_name": file_name, "notes": notes})
        return out

    # ------------------------------------------------------------------ savings
    async def savings(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        threshold = await self._threshold(app_uuid)
        lic_rows = (await self.db.execute(
            select(License.seats_purchased, License.seats_assigned, License.seats_active, License.total_annual_cost_cents,
                   License.utilization_pct, License.waste_seats, License.waste_cost_cents, License.currency,
                   License.billing_cycle).where(License.app_id == app_uuid))).all()
        licenses = [{"seats_purchased": a, "seats_assigned": b, "seats_active": c, "annual_cost_cents": d,
                     "utilization_pct": float(e) if e is not None else None, "waste_seats": f, "waste_cost_cents": g,
                     "currency": h, "billing_cycle": i} for a, b, c, d, e, f, g, h, i in lic_rows]

        svc = ReclamationService(self.db)
        scope = await svc.counted_apps()
        signal = scope["counted"].get(app_uuid)
        reclaim = {"counted": signal is not None, "signal": signal or "okta", "inactive_days": min(max(threshold, 14), 90),
                   "inactive": None, "potential_cents": None, "per_seat_cents": None}
        if signal:
            cutoff = datetime.now(timezone.utc) - timedelta(days=reclaim["inactive_days"])
            inactive, aged = svc._inactive_conditions(cutoff)
            people = (await self.db.execute(
                select(AppUser.role_in_app).where(AppUser.app_id == app_uuid, inactive, aged))).all()
            per_seat = (await svc.seat_costs()).get(app_uuid)
            reclaim["inactive"] = len(people)
            reclaim["per_seat_cents"] = per_seat
            if per_seat is not None:
                reclaim["potential_cents"] = sum(seat_savings_cents(label, per_seat) or 0 for (label,) in people)

        by_status = {s: (0, 0) for s in ("open", "approved", "reclaimed")}
        for status, n, total in (await self.db.execute(
                select(ReclamationItem.status, func.count(ReclamationItem.id), func.sum(ReclamationItem.est_annual_savings_cents))
                .where(ReclamationItem.app_id == app_uuid).group_by(ReclamationItem.status))).all():
            if status in by_status:
                by_status[status] = (int(n), int(total or 0))
        in_review_n = by_status["open"][0] + by_status["approved"][0]
        return {"licenses": licenses, "reclamation": reclaim,
                "in_review": {"count": in_review_n, "cents": by_status["open"][1] + by_status["approved"][1],
                              "approved": by_status["approved"][0]},
                "reclaimed": {"count": by_status["reclaimed"][0], "cents": by_status["reclaimed"][1]}}

    # ------------------------------------------------------------------ payments
    async def payments(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        rows = (await self.db.execute(
            select(AppPayment.id, AppPayment.paid_on, AppPayment.amount_cents, AppPayment.currency, AppPayment.reference,
                   AppPayment.notes).where(AppPayment.app_id == app_uuid).order_by(AppPayment.paid_on.desc()))).all()
        payments = [{"id": str(i), "paid_on": _iso(d), "amount_cents": a, "currency": c, "reference": r, "notes": n}
                    for i, d, a, c, r, n in rows]
        today = datetime.now(timezone.utc).date()
        year_ago = today - timedelta(days=365)
        lic = (await self.db.execute(
            select(License.total_annual_cost_cents, License.billing_cycle, License.next_billing_date, License.currency)
            .where(License.app_id == app_uuid))).all()
        expected = []
        for annual, cycle, next_date, currency in lic:
            if not annual:
                continue
            amount = round(annual / 12) if (cycle or "").lower() == "monthly" else annual
            expected.append({"next_billing_date": _iso(next_date), "billing_cycle": cycle or "annual",
                             "amount_cents": amount, "currency": currency})
        return {"payments": payments, "expected": expected,
                "paid_last_12_months_cents": sum(p["amount_cents"] for p in payments
                                                 if date.fromisoformat(p["paid_on"]) >= year_ago),
                "annual_cost_cents": sum(a or 0 for a, *_ in lic)}

    async def add_payment(self, app_id, payload: dict):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return False, "That app no longer exists."
        try:
            paid_on = date.fromisoformat(str(payload.get("paid_on")))
        except ValueError:
            return False, "Enter the payment date as YYYY-MM-DD."
        try:
            cents = int(round(float(payload.get("amount_usd")) * 100))
        except (TypeError, ValueError):
            return False, "Enter the amount as a number."
        if cents <= 0 or cents > 10_000_000_000:
            return False, "The amount must be greater than zero."
        currency = (_text(payload.get("currency"), 20) or "USD").upper()          # validate the whole value, never a truncation of it
        if not re.fullmatch(r"[A-Z]{3}", currency):
            return False, "The currency must be a 3-letter code such as USD."
        ptype = payload.get("payment_type") or "ap"
        if ptype not in ("ap", "expense"):
            return False, "The payment type must be AP or expense."
        self.db.add(AppPayment(app_id=app_uuid, paid_on=paid_on, amount_cents=cents, currency=currency, payment_type=ptype, source="manual",
                               reference=_text(payload.get("reference"), 255), notes=_text(payload.get("notes"), 2000)))
        await record_event(self.db, app_uuid, "payment", f"Payment recorded: {_usd(cents)} {currency} on {paid_on:%b %-d, %Y}")
        await self.db.commit()
        return True, "Saved."

    async def delete_payment(self, app_id, payment_id) -> bool:
        app_uuid, pid = parse_uuid(app_id), parse_uuid(payment_id)
        if app_uuid is None or pid is None:
            return False
        await self.db.execute(delete(AppPayment).where(AppPayment.id == pid, AppPayment.app_id == app_uuid))
        await record_event(self.db, app_uuid, "payment", "A payment record was removed")
        await self.db.commit()
        return True

    # ------------------------------------------------------------------ documents
    async def documents(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        rows = (await self.db.execute(
            select(AppDocument.id, AppDocument.title, AppDocument.url, AppDocument.doc_type, AppDocument.created_at)
            .where(AppDocument.app_id == app_uuid).order_by(AppDocument.created_at.desc()))).all()
        return [{"id": str(i), "title": t, "url": u, "doc_type": d, "created_at": _iso(c)} for i, t, u, d, c in rows]

    async def add_document(self, app_id, payload: dict):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return False, "That app no longer exists."
        title, url = _text(payload.get("title"), 255), _text(payload.get("url"), 1000)
        if not title:
            return False, "Give the document a title."
        if not url or not re.match(r"^https?://", url, re.I):
            return False, "The link must start with http:// or https://"
        doc_type = payload.get("doc_type") if payload.get("doc_type") in DOC_TYPES else "other"
        self.db.add(AppDocument(app_id=app_uuid, title=title, url=url, doc_type=doc_type))
        await record_event(self.db, app_uuid, "document", f"Document added: {title}")
        await self.db.commit()
        return True, "Saved."

    async def delete_document(self, app_id, doc_id) -> bool:
        app_uuid, did = parse_uuid(app_id), parse_uuid(doc_id)
        if app_uuid is None or did is None:
            return False
        await self.db.execute(delete(AppDocument).where(AppDocument.id == did, AppDocument.app_id == app_uuid))
        await record_event(self.db, app_uuid, "document", "A document was removed")
        await self.db.commit()
        return True

    # ------------------------------------------------------------------ sentiment
    async def sentiment(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        rows = (await self.db.execute(
            select(AppFeedback.id, AppFeedback.rating, AppFeedback.person, AppFeedback.comment, AppFeedback.created_at)
            .where(AppFeedback.app_id == app_uuid).order_by(AppFeedback.created_at.desc()).limit(500))).all()
        entries = [{"id": str(i), "rating": r, "person": p, "comment": c, "created_at": _iso(d)} for i, r, p, c, d in rows]
        dist = {str(n): sum(1 for e in entries if e["rating"] == n) for n in range(1, 6)}
        return {"count": len(entries), "average": round(sum(e["rating"] for e in entries) / len(entries), 2) if entries else None,
                "distribution": dist, "entries": entries}

    async def add_feedback(self, app_id, payload: dict):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return False, "That app no longer exists."
        try:
            rating = int(payload.get("rating"))
        except (TypeError, ValueError):
            return False, "Pick a rating from 1 to 5."
        if not 1 <= rating <= 5:
            return False, "Pick a rating from 1 to 5."
        person = _text(payload.get("person"), 255)
        self.db.add(AppFeedback(app_id=app_uuid, rating=rating, person=person, comment=_text(payload.get("comment"), 4000)))
        await record_event(self.db, app_uuid, "sentiment", f"Feedback logged: {rating}/5" + (f" from {person}" if person else ""))
        await self.db.commit()
        return True, "Saved."

    async def delete_feedback(self, app_id, feedback_id) -> bool:
        app_uuid, fid = parse_uuid(app_id), parse_uuid(feedback_id)
        if app_uuid is None or fid is None:
            return False
        await self.db.execute(delete(AppFeedback).where(AppFeedback.id == fid, AppFeedback.app_id == app_uuid))
        await self.db.commit()
        return True

    # ------------------------------------------------------------------ history
    async def history(self, app_id, limit: int = 200):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        rows = (await self.db.execute(
            select(AppEvent.id, AppEvent.kind, AppEvent.detail, AppEvent.created_at)
            .where(AppEvent.app_id == app_uuid).order_by(AppEvent.created_at.desc()).limit(limit))).all()
        return [{"id": str(i), "kind": k, "detail": d, "created_at": _iso(c)} for i, k, d, c in rows]

    # ------------------------------------------------------------------ overview metrics
    async def metrics(self, app_id):
        """Everything on the Overview tab's cards and charts."""
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        now = datetime.now(timezone.utc)
        today = now.date()
        threshold = await self._threshold(app_uuid)
        settings_row = (await self.db.execute(select(AppSetting.certifications).where(AppSetting.app_id == app_uuid))).scalar_one_or_none()

        # provisioned vs active, by the app's activity threshold
        cutoff = now - timedelta(days=threshold)
        people = (await self.db.execute(select(AppUser.last_login_at, AppUser.role_in_app).where(AppUser.app_id == app_uuid))).all()
        def is_active(last):
            last = last.replace(tzinfo=timezone.utc) if last is not None and last.tzinfo is None else last
            return last is not None and last >= cutoff
        active = sum(1 for last, _label in people if is_active(last))
        provisioned = {"total": len(people), "active": active, "inactive": len(people) - active,
                       "by_license": dict(Counter((label or "unlabelled") for _l, label in people))}

        # licences, contracts, payments
        lic = (await self.db.execute(
            select(License.seats_purchased, License.seats_assigned, License.seats_active, License.total_annual_cost_cents,
                   License.utilization_pct, License.waste_cost_cents, License.next_billing_date).where(License.app_id == app_uuid))).all()
        seats = None
        if lic:
            seats = {"purchased": sum(r[0] or 0 for r in lic), "assigned": sum(r[1] or 0 for r in lic), "active": sum(r[2] or 0 for r in lic),
                     "annual_cost_cents": sum(r[3] or 0 for r in lic), "waste_cost_cents": sum(r[5] or 0 for r in lic),
                     "utilization_pct": next((float(r[4]) for r in lic if r[4] is not None), None)}
        contracts = (await self.db.execute(
            select(Contract.status, Contract.end_date, Contract.auto_renews, Contract.total_value_cents).where(Contract.app_id == app_uuid))).all()
        live = [(end, auto) for status, end, auto, _v in contracts if _enum(status) == "active" and end and end >= today]
        renewal = {"date": None, "days": None, "source": None, "auto_renews": None}
        if live:
            end, auto = min(live, key=lambda c: c[0])
            renewal = {"date": end.isoformat(), "days": (end - today).days, "source": "contract", "auto_renews": bool(auto)}
        else:
            billing = sorted(r[6] for r in lic if r[6] and r[6] >= today)
            if billing:
                renewal = {"date": billing[0].isoformat(), "days": (billing[0] - today).days, "source": "license", "auto_renews": None}
        pay = await self.payments(app_id)
        contract_value = sum(v or 0 for status, _e, _a, v in contracts if _enum(status) == "active")

        # active users over time: only where per-day activity is recorded
        series = None
        day_rows = (await self.db.execute(
            select(UserActiveDay.user_id, UserActiveDay.day).where(UserActiveDay.app_id == app_uuid,
                                                                   UserActiveDay.day >= today - timedelta(days=100)).limit(400000))).all()
        if day_rows:
            window = min(max(threshold, 7), 60)
            first = min(d for _u, d in day_rows)
            start = max(first + timedelta(days=window - 1), today - timedelta(days=89))   # earlier days would undercount: their window isn't fully recorded
            if start <= today:
                series = {"window_days": window, "history_start": first.isoformat(), "points": rolling_active_counts(day_rows, start, today, window)}

        return {"app": {"id": str(app_uuid), "name": app[1]}, "threshold": threshold, "renewal": renewal, "provisioned": provisioned, "seats": seats,
                "payments": {"paid_last_12_months_cents": pay["paid_last_12_months_cents"], "annual_cost_cents": pay["annual_cost_cents"],
                             "contract_value_cents": contract_value, "expected": pay["expected"],
                             "ledger": [{"paid_on": p["paid_on"], "amount_cents": p["amount_cents"]} for p in pay["payments"]]},
                "active_series": series, "certifications": settings_row or []}

    # ------------------------------------------------------------------ alerts
    async def alerts(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        now = datetime.now(timezone.utc)
        contracts = []
        for c in (await self.contracts(app_id)) or []:
            end = date.fromisoformat(c["end_date"]) if c["end_date"] else None
            contracts.append({"id": c["id"], "status": c["status"], "end_date": end, "auto_renews": c["auto_renews"],
                              "cancel_by": date.fromisoformat(c["cancel_by"]) if c["cancel_by"] else None})
        sav = await self.savings(app_id)
        assigned = (await self.db.execute(select(func.count(AppUser.id)).where(AppUser.app_id == app_uuid))).scalar_one()
        settings = await self.get_settings(app_id)

        issues = []
        for key, target, status, last_sync in (await self.db.execute(
                select(ConnectorConfig.key, ConnectorConfig.target_app_id, ConnectorConfig.sync_status, ConnectorConfig.last_sync_at))).all():
            if key != "okta_activity" and target != app_uuid:
                continue
            name = CONNECTOR_NAMES.get(key, key)
            if status == "error":
                issues.append({"key": key, "title": f"The {name} sync is failing",
                               "detail": "Activity for this app may be out of date. Check the Integration Library."})
            elif last_sync is not None and (now - last_sync).days >= 3:
                issues.append({"key": key, "title": f"{name} hasn't synced in {(now - last_sync).days} days",
                               "detail": "Activity for this app may be out of date."})
        pending = sav["in_review"]["approved"]
        has_cost = any(l["annual_cost_cents"] for l in sav["licenses"])
        return build_alerts({
            "today": now.date(), "contracts": contracts, "licenses": sav["licenses"], "assigned": assigned,
            "inactive": sav["reclamation"]["inactive"], "inactive_days": sav["reclamation"]["inactive_days"],
            "potential_cents": sav["reclamation"]["potential_cents"], "signal": sav["reclamation"]["signal"],
            "connector_issues": issues, "pending_removals": pending, "has_cost": has_cost,
            "owner": settings["info"]["owner_email"] or settings["info"]["business_owner"], "is_shadow_it": settings["base"]["is_shadow_it"]})

    # ------------------------------------------------------------------ saved filters
    async def saved_filters(self, app_id):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return None
        rows = (await self.db.execute(
            select(SavedFilter.id, SavedFilter.app_id, SavedFilter.name, SavedFilter.config)
            .where((SavedFilter.app_id == app_uuid) | (SavedFilter.app_id.is_(None))).order_by(SavedFilter.name))).all()
        return [{"id": str(i), "name": n, "config": c, "shared": a is None} for i, a, n, c in rows]

    async def add_saved_filter(self, app_id, payload: dict):
        app_uuid, app = await self._app(app_id)
        if app is None:
            return False, "That app no longer exists."
        name, config = _text(payload.get("name"), 120), clean_filter_config(payload.get("config"))
        if not name:
            return False, "Give the filter a name."
        if config is None:
            return False, "That filter couldn't be saved."
        self.db.add(SavedFilter(app_id=None if payload.get("all_apps") else app_uuid, name=name, config=config))
        await self.db.commit()
        return True, "Saved."

    async def delete_saved_filter(self, filter_id) -> bool:
        fid = parse_uuid(filter_id)
        if fid is None:
            return False
        await self.db.execute(delete(SavedFilter).where(SavedFilter.id == fid))
        await self.db.commit()
        return True

    # ------------------------------------------------------------------ HR roster
    async def roster_count(self) -> int:
        return int((await self.db.execute(select(func.count()).select_from(EmployeeRoster))).scalar_one() or 0)

    async def replace_roster(self, text: str):
        emails = parse_roster(text)
        if not emails:
            return False, "No email addresses were found.", 0
        if len(emails) > MAX_ROSTER:
            return False, f"That's more than {MAX_ROSTER:,} emails.", 0
        await self.db.execute(delete(EmployeeRoster))
        self.db.add_all([EmployeeRoster(email=e) for e in emails])
        await self.db.commit()
        return True, f"Saved {len(emails):,} employees.", len(emails)
