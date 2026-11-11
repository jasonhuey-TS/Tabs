"""The Payments page: totals and breakdowns across every app, filters and saved views, and loading payments from a file."""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timezone

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import App
from app.models.app_extras import AppAlias, AppPayment, PaymentFilter
from app.models.reclamation import ReclamationSetting
from app.services import payment_import as pi
from app.services.app_details_service import AppDetailsService
from app.services.app_events import record_event
from app.services.reclamation_service import parse_uuid, to_csv

FISCAL_KEY = "fiscal_year_start_month"
MAX_IMPORT_CHARS = 15_000_000
INSERT_CHUNK = 2000
MAX_EXPORT = 100_000


def _iso(value):
    return value.isoformat() if value else None


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _usd(cents):
    return f"${cents / 100:,.0f}"


def fiscal_start(today: date, start_month: int) -> date:
    """First day of the fiscal year that contains `today`."""
    return date(today.year if today.month >= start_month else today.year - 1, start_month, 1)


def clean_payment_filter(config):
    if not isinstance(config, dict):
        return None
    out = {"q": str(config.get("q") or "").strip()[:100], "type": config.get("type") if config.get("type") in ("ap", "expense") else "",
           "source": config.get("source") if config.get("source") in ("manual", "csv") else "",
           "date_from": _iso(_date(config.get("date_from"))) or "", "date_to": _iso(_date(config.get("date_to"))) or ""}
    return out


class PaymentsService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ settings
    async def fiscal_month(self) -> int:
        raw = (await self.db.execute(select(ReclamationSetting.value).where(ReclamationSetting.key == FISCAL_KEY))).scalar_one_or_none()
        try:
            month = int(raw)
        except (TypeError, ValueError):
            return 1
        return month if 1 <= month <= 12 else 1

    async def save_fiscal_month(self, month):
        try:
            month = int(month)
        except (TypeError, ValueError):
            return False, "Pick a month."
        if not 1 <= month <= 12:
            return False, "Pick a month from 1 to 12."
        row = (await self.db.execute(select(ReclamationSetting).where(ReclamationSetting.key == FISCAL_KEY))).scalar_one_or_none()
        if row is None:
            self.db.add(ReclamationSetting(key=FISCAL_KEY, value=str(month)))
        else:
            row.value = str(month)
        await self.db.commit()
        return True, "Saved."

    # ------------------------------------------------------------------ the page
    def _conds(self, f: dict) -> list:
        conds = []
        if f.get("type") in ("ap", "expense"):
            conds.append(AppPayment.payment_type == f["type"])
        if _date(f.get("date_from")):
            conds.append(AppPayment.paid_on >= _date(f["date_from"]))
        if _date(f.get("date_to")):
            conds.append(AppPayment.paid_on <= _date(f["date_to"]))
        if f.get("source") in ("manual", "csv"):
            conds.append(AppPayment.source == f["source"])
        if f.get("app_id") and parse_uuid(f["app_id"]):
            conds.append(AppPayment.app_id == parse_uuid(f["app_id"]))
        q = (f.get("q") or "").strip()
        if q:
            conds.append(or_(App.name.icontains(q, autoescape=True), App.vendor.icontains(q, autoescape=True),
                             AppPayment.reference.icontains(q, autoescape=True)))
        return conds

    async def summary(self, f: dict) -> dict:
        today = datetime.now(timezone.utc).date()
        month = await self.fiscal_month()
        ytd_start, fy_start = date(today.year, 1, 1), fiscal_start(today, month)
        conds, amount = self._conds(f), AppPayment.amount_cents
        rows = (await self.db.execute(
            select(AppPayment.app_id, App.name, AppPayment.payment_type, func.sum(amount), func.count(AppPayment.id), func.max(AppPayment.paid_on),
                   func.sum(case((AppPayment.paid_on >= ytd_start, amount), else_=0)),
                   func.sum(case((AppPayment.paid_on >= fy_start, amount), else_=0)))
            .select_from(AppPayment).join(App, App.id == AppPayment.app_id)
            .where(*conds, AppPayment.currency == "USD")
            .group_by(AppPayment.app_id, App.name, AppPayment.payment_type))).all()
        non_usd = (await self.db.execute(
            select(func.count(AppPayment.id)).select_from(AppPayment).join(App, App.id == AppPayment.app_id)
            .where(*conds, AppPayment.currency != "USD"))).scalar_one()
        in_system = (await self.db.execute(select(func.count(AppPayment.id)))).scalar_one()

        apps = {}
        for app_id, name, ptype, total, n, last, ytd, fytd in rows:
            a = apps.setdefault(str(app_id), {"app_id": str(app_id), "name": name, "ap_cents": 0, "expense_cents": 0, "total_cents": 0,
                                              "ytd_cents": 0, "fiscal_ytd_cents": 0, "count": 0, "last_paid": None})
            a["expense_cents" if ptype == "expense" else "ap_cents"] += int(total or 0)
            a["total_cents"] += int(total or 0)
            a["ytd_cents"] += int(ytd or 0)
            a["fiscal_ytd_cents"] += int(fytd or 0)
            a["count"] += int(n or 0)
            if last and (a["last_paid"] is None or last.isoformat() > a["last_paid"]):
                a["last_paid"] = last.isoformat()
        ordered = sorted(apps.values(), key=lambda a: (-a["total_cents"], a["name"]))
        return {"kpis": {"total_cents": sum(a["total_cents"] for a in ordered), "ap_cents": sum(a["ap_cents"] for a in ordered),
                         "expense_cents": sum(a["expense_cents"] for a in ordered), "ytd_cents": sum(a["ytd_cents"] for a in ordered),
                         "fiscal_ytd_cents": sum(a["fiscal_ytd_cents"] for a in ordered), "applications": len(ordered)},
                "apps": ordered, "fiscal_year_start_month": month, "fiscal_year_start": fy_start.isoformat(),
                "non_usd_excluded": int(non_usd or 0), "payments_in_system": int(in_system or 0)}

    async def for_app(self, app_id: str, f: dict) -> list:
        rows = (await self.db.execute(
            select(AppPayment.id, AppPayment.paid_on, AppPayment.amount_cents, AppPayment.currency, AppPayment.payment_type,
                   AppPayment.reference, AppPayment.source)
            .select_from(AppPayment).join(App, App.id == AppPayment.app_id)
            .where(*self._conds({**f, "app_id": app_id})).order_by(AppPayment.paid_on.desc()).limit(1000))).all()
        return [{"id": str(i), "paid_on": _iso(d), "amount_cents": a, "currency": c, "payment_type": t, "reference": r, "source": s}
                for i, d, a, c, t, r, s in rows]

    async def export_csv(self, f: dict) -> str:
        rows = (await self.db.execute(
            select(App.name, AppPayment.paid_on, AppPayment.amount_cents, AppPayment.currency, AppPayment.payment_type, AppPayment.reference, AppPayment.source)
            .select_from(AppPayment).join(App, App.id == AppPayment.app_id)
            .where(*self._conds(f)).order_by(AppPayment.paid_on.desc()).limit(MAX_EXPORT))).all()
        data = [{"app": n, "date": _iso(d), "amount": a / 100.0, "currency": c, "type": "Expense" if t == "expense" else "AP", "reference": r or "", "source": s}
                for n, d, a, c, t, r, s in rows]
        return to_csv(data, [("app", "Application"), ("date", "Payment date"), ("amount", "Amount"), ("currency", "Currency"),
                             ("type", "Type"), ("reference", "Reference"), ("source", "Source")])

    async def delete(self, payment_id: str) -> bool:
        pid = parse_uuid(payment_id)
        if pid is None:
            return False
        app_id = (await self.db.execute(select(AppPayment.app_id).where(AppPayment.id == pid))).scalar_one_or_none()
        if app_id is None:
            return False
        await self.db.execute(delete(AppPayment).where(AppPayment.id == pid))
        await record_event(self.db, app_id, "payment", "A payment record was removed")
        await self.db.commit()
        return True

    # ------------------------------------------------------------------ saved views
    async def saved_filters(self) -> list:
        rows = (await self.db.execute(select(PaymentFilter.id, PaymentFilter.name, PaymentFilter.config).order_by(PaymentFilter.name))).all()
        return [{"id": str(i), "name": n, "config": c} for i, n, c in rows]

    async def add_saved_filter(self, payload: dict):
        name, config = (str(payload.get("name") or "").strip()[:120]), clean_payment_filter(payload.get("config"))
        if not name:
            return False, "Give the filter a name."
        if config is None:
            return False, "That filter couldn't be saved."
        self.db.add(PaymentFilter(name=name, config=config))
        await self.db.commit()
        return True, "Saved."

    async def delete_saved_filter(self, filter_id: str) -> bool:
        fid = parse_uuid(filter_id)
        if fid is None:
            return False
        await self.db.execute(delete(PaymentFilter).where(PaymentFilter.id == fid))
        await self.db.commit()
        return True

    # ------------------------------------------------------------------ loading payments from a file
    async def _plan(self, text, mapping, default_type, decisions):
        if len(text or "") > MAX_IMPORT_CHARS:
            return None, {"error": "That file is too large (15 MB maximum)."}
        headers, rows = pi.parse_csv(text)
        if not headers:
            return None, {"error": "That file is empty or isn't a CSV."}
        if not rows:
            return None, {"error": "The file has a header row but no payments."}
        chosen = {f: h for f, h in (mapping or {}).items() if f in pi.FIELDS and h in headers} if mapping else pi.detect_mapping(headers)
        default_type = default_type if default_type in ("ap", "expense") else "ap"
        apps = [(str(i), n, v) for i, n, v in (await self.db.execute(select(App.id, App.name, App.vendor))).all()]
        aliases = {a: str(i) for a, i in (await self.db.execute(select(AppAlias.alias, AppAlias.app_id))).all()}
        clean_decisions = {k: v for k, v in (decisions or {}).items() if v == "skip" or any(v == a[0] for a in apps)}
        plan = pi.plan_import(rows, chosen, default_type, apps, aliases, clean_decisions)
        return {"headers": headers, "rows": rows, "mapping": chosen, "plan": plan, "decisions": clean_decisions}, None

    async def _existing_ids(self, ids: list) -> set:
        found = set()
        for i in range(0, len(ids), INSERT_CHUNK):
            chunk = ids[i:i + INSERT_CHUNK]
            found |= {e for (e,) in (await self.db.execute(
                select(AppPayment.external_id).where(AppPayment.source == "csv", AppPayment.external_id.in_(chunk)))).all()}
        return found

    async def import_preview(self, text, mapping=None, default_type="ap", decisions=None) -> dict:
        ctx, error = await self._plan(text, mapping, default_type, decisions)
        if error:
            return error
        plan = ctx["plan"]
        if plan["error"]:
            return {"headers": ctx["headers"], "mapping": ctx["mapping"], "total_rows": len(ctx["rows"]), "error": plan["error"],
                    "sample": ctx["rows"][:5], "ready": 0, "unmatched": [], "invalid": {"count": 0, "sample": []}}
        ready = plan["ready"]
        existing = await self._existing_ids([r["external_id"] for r in ready])
        new = [r for r in ready if r["external_id"] not in existing]
        return {"error": None, "headers": ctx["headers"], "mapping": ctx["mapping"], "sample": ctx["rows"][:5], "total_rows": len(ctx["rows"]),
                "ready": len(new), "ready_total_cents": sum(r["amount_cents"] for r in new), "already_imported": len(ready) - len(new),
                "apps": len({r["app_id"] for r in new}), "skipped": plan["skipped"],
                "invalid": {"count": len(plan["invalid"]), "sample": plan["invalid"][:20]},
                "unmatched": plan["unmatched"][:200], "unmatched_rows": sum(u["rows"] for u in plan["unmatched"])}

    async def import_commit(self, text, mapping, default_type="ap", decisions=None, file_name="upload.csv") -> dict:
        ctx, error = await self._plan(text, mapping, default_type, decisions)
        if error:
            return {"ok": False, **error}
        plan = ctx["plan"]
        if plan["error"]:
            return {"ok": False, "error": plan["error"]}
        ready = plan["ready"]
        existing = await self._existing_ids([r["external_id"] for r in ready])
        new = [r for r in ready if r["external_id"] not in existing]

        # remember the matches you chose, so the next file matches by itself
        for vendor, app_id in ctx["decisions"].items():
            key = pi.normalize_vendor(vendor)
            if app_id == "skip" or not key:
                continue
            row = (await self.db.execute(select(AppAlias).where(AppAlias.alias == key))).scalar_one_or_none()
            if row is None:
                self.db.add(AppAlias(alias=key, app_id=parse_uuid(app_id)))
            else:
                row.app_id = parse_uuid(app_id)

        batch = uuid.uuid4().hex
        for i in range(0, len(new), INSERT_CHUNK):
            await self.db.execute(pg_insert(AppPayment).values([
                {"id": uuid.uuid4(), "app_id": parse_uuid(r["app_id"]), "paid_on": r["paid_on"], "amount_cents": r["amount_cents"],
                 "currency": r["currency"], "reference": r["reference"], "payment_type": r["payment_type"], "source": "csv",
                 "external_id": r["external_id"], "import_batch": batch} for r in new[i:i + INSERT_CHUNK]]).on_conflict_do_nothing())

        per_app = Counter(r["app_id"] for r in new)
        totals = Counter()
        for r in new:
            totals[r["app_id"]] += r["amount_cents"]
        for app_id, n in list(per_app.items())[:500]:
            await record_event(self.db, parse_uuid(app_id), "payment",
                               f"Imported {n:,} payment{'s' if n != 1 else ''} ({_usd(totals[app_id])}) from {str(file_name)[:80]}")
        await self.db.commit()
        return {"ok": True, "error": None, "imported": len(new), "already_imported": len(ready) - len(new), "apps": len(per_app),
                "imported_cents": sum(r["amount_cents"] for r in new), "skipped": plan["skipped"], "invalid": len(plan["invalid"]),
                "unmatched_rows": sum(u["rows"] for u in plan["unmatched"]), "batch": batch}
