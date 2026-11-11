"""Portfolio-wide numbers for the Analytics page: spend, payments over time, owners, new apps, savings.

Payments come from the payments you've loaded (Payments > Payment Uploads, or added by hand); everything else comes from
the app list. Nothing here is estimated: when a number can't be known yet, the page says why instead of showing a zero.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import App
from app.models.app_extras import AppPayment, AppSetting
from app.models.reclamation import ReclamationItem

ADDED_DAYS = 90
NO_PAYMENT_MONTHS = 15
CHART_MONTHS = 36
MAX_LIST = 500


def months_ago(today: date, n: int) -> date:
    y, m = today.year, today.month - n
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, min(today.day, 28))


def month_iso(value) -> str:
    return f"{value.year:04d}-{value.month:02d}-01"


def detect_initial_import(top_day, top_count: int, total_apps: int):
    """If most apps were first seen on one day, that was Tab's first sync, not apps genuinely 'added'. Returns that date or None."""
    if top_day is not None and total_apps and top_count >= max(20, total_apps / 2):
        return top_day
    return None


class AnalyticsService:
    def __init__(self, db):
        self.db = db

    async def portfolio(self) -> dict:
        now = datetime.now(timezone.utc)
        today = now.date()
        year_ago = today - timedelta(days=365)
        amount = AppPayment.amount_cents
        usd = AppPayment.currency == "USD"

        total_apps = int((await self.db.execute(select(func.count(App.id)))).scalar_one() or 0)

        by_type = {t: (int(s or 0), int(n or 0)) for t, s, n in (await self.db.execute(
            select(AppPayment.payment_type, func.sum(amount), func.count(func.distinct(AppPayment.app_id)))
            .where(AppPayment.paid_on >= year_ago, usd).group_by(AppPayment.payment_type))).all()}
        ap, expense = by_type.get("ap", (0, 0)), by_type.get("expense", (0, 0))
        non_usd = int((await self.db.execute(select(func.count(AppPayment.id)).where(
            AppPayment.paid_on >= year_ago, AppPayment.currency != "USD"))).scalar_one() or 0)

        month = func.date_trunc("month", AppPayment.paid_on)
        monthly = [{"month": month_iso(m), "cents": int(c or 0)} for m, c in (await self.db.execute(
            select(month, func.sum(amount)).where(usd, AppPayment.paid_on >= months_ago(today, CHART_MONTHS).replace(day=1))
            .group_by(month).order_by(month))).all()]
        in_system = int((await self.db.execute(select(func.count(AppPayment.id)))).scalar_one() or 0)

        recent = select(AppPayment.app_id).where(AppPayment.paid_on >= months_ago(today, NO_PAYMENT_MONTHS))
        no_payment = int((await self.db.execute(select(func.count(App.id)).where(App.id.not_in(recent)))).scalar_one() or 0)

        owner = func.coalesce(func.nullif(func.trim(App.owner_email), ""), func.nullif(func.trim(AppSetting.owner_email), ""),
                              func.nullif(func.trim(AppSetting.business_owner), ""))
        owner_free = (select(App.id, App.name).select_from(App).outerjoin(AppSetting, AppSetting.app_id == App.id).where(owner.is_(None)))
        no_owner_rows = (await self.db.execute(owner_free.order_by(App.name).limit(MAX_LIST))).all()
        no_owner_count = int((await self.db.execute(
            select(func.count(App.id)).select_from(App).outerjoin(AppSetting, AppSetting.app_id == App.id).where(owner.is_(None)))).scalar_one() or 0)

        first_day = func.date(App.first_seen_at)
        top = (await self.db.execute(select(first_day, func.count(App.id)).group_by(first_day).order_by(func.count(App.id).desc()).limit(1))).first()
        initial = detect_initial_import(top[0] if top else None, int(top[1]) if top else 0, total_apps)
        added_conds = [App.first_seen_at >= now - timedelta(days=ADDED_DAYS)]
        if initial is not None:
            added_conds.append(first_day != initial)
        added = (await self.db.execute(select(App.id, App.name, App.first_seen_at, App.discovered_via).where(*added_conds)
                                       .order_by(App.first_seen_at.desc()).limit(MAX_LIST))).all()
        spend = {}
        if added:
            spend = {a: int(s or 0) for a, s in (await self.db.execute(
                select(AppPayment.app_id, func.sum(amount)).where(AppPayment.app_id.in_([r[0] for r in added]),
                                                                  AppPayment.paid_on >= year_ago, usd).group_by(AppPayment.app_id))).all()}

        saved_month = func.date_trunc("month", ReclamationItem.decided_at)
        savings = [{"month": month_iso(m), "cents": int(c or 0), "people": int(n or 0)} for m, c, n in (await self.db.execute(
            select(saved_month, func.sum(ReclamationItem.est_annual_savings_cents), func.count(ReclamationItem.id))
            .where(ReclamationItem.status == "reclaimed", ReclamationItem.decided_at.is_not(None))
            .group_by(saved_month).order_by(saved_month))).all()]

        return {
            "app_count": total_apps,
            "payments": {"has_data": in_system > 0, "annual_cents": ap[0] + expense[0], "ap_cents": ap[0], "expense_cents": expense[0],
                         "apps_with_expense": expense[1], "non_usd_excluded": non_usd, "monthly": monthly},
            "no_payment": {"count": no_payment, "months": NO_PAYMENT_MONTHS, "payments_loaded": in_system > 0},
            "no_owner": {"count": no_owner_count, "total": total_apps, "pct": round(100.0 * no_owner_count / total_apps, 1) if total_apps else 0.0,
                         "apps": [{"app_id": str(i), "name": n} for i, n in no_owner_rows]},
            "added": {"days": ADDED_DAYS, "initial_import_date": initial.isoformat() if initial else None, "total": len(added),
                      "rows": [{"app_id": str(i), "name": n, "first_seen": f.isoformat() if f else None, "source": s or "unknown",
                                "annual_cents": spend.get(i, 0)} for i, n, f, s in added]},
            "savings": {"monthly": savings, "total_cents": sum(s["cents"] for s in savings)},
        }
