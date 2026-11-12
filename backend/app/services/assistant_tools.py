"""What the assistant can look up. Every tool is read-only and returns three things:

  headline    one plain sentence, written by us from the numbers (so it is always accurate)
  table       the full detail, shown to the person exactly as the database has it
  model_view  a short summary for the AI, if one is in use: totals and app names only, never people's names or emails

Nothing here changes any data.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select

from app.models import App, AppUser, License, User
from app.models.app_extras import AppPayment, AppSetting, EmployeeRoster
from app.models.contract import Contract
from app.models.user_profile import UserProfile
from app.services.analytics_service import detect_initial_import
from app.services.payments_service import PaymentsService
from app.services.reclamation_service import ReclamationService

GONE_STATUSES = ("DEPROVISIONED", "SUSPENDED")           # Okta says these people no longer have working access
ENDED_CONTRACT = ("expired", "cancelled")
MAX_ROWS = 500


def clamp(value, low, high, default):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def money(cents) -> str:
    return f"${(cents or 0) / 100:,.0f}"


def col(key, label, kind="text"):
    return {"key": key, "label": label, "type": kind}


def table(title, columns, rows, total=None):
    return {"title": title, "columns": columns, "rows": rows, "total": len(rows) if total is None else total}


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


# --------------------------------------------------------------------------- unused licenses
async def underutilized_apps(db, days=60, limit=25):
    days, limit = clamp(days, 14, 90, 60), clamp(limit, 1, 100, 25)
    ov = await ReclamationService(db).overview(days)
    k = ov.get("kpis")
    if not ov.get("ready") or not k:
        return {"headline": "There isn't enough verified sign-in data yet to say which licenses are unused. Connect an activity source, "
                            "or mark an app as trusted on the Reclamation page.", "model_view": {"ready": False}, "table": None}
    rows = [{"app_id": r["app_id"], "name": r["name"], "assigned": r["assigned"], "inactive": r["inactive"], "inactive_pct": r["inactive_pct"],
             "savings": r["est_annual_savings_cents"]} for r in ov["by_app"][:limit]]
    headline = (f"{k['inactive']:,} of {k['assigned']:,} licenses ({k['inactive_pct']}%) across {k['apps_with_opportunities']:,} {plural(k['apps_with_opportunities'], 'app')} have had no sign-in "
                f"for {days}+ days")
    headline += f", about {money(k['est_annual_savings_cents'])} a year if they were removed." if k["est_annual_savings_cents"] else "."
    if k["apps_missing_cost"]:
        headline += f" {k['apps_missing_cost']:,} {plural(k['apps_missing_cost'], 'app has', 'apps have')} no seat cost on file, so their savings aren't counted."
    return {"headline": headline,
            "model_view": {"days": days, "licenses_assigned": k["assigned"], "licenses_inactive": k["inactive"], "inactive_pct": k["inactive_pct"],
                           "est_annual_savings_usd": round((k["est_annual_savings_cents"] or 0) / 100), "apps_with_opportunities": k["apps_with_opportunities"],
                           "apps_missing_seat_cost": k["apps_missing_cost"],
                           "top_apps": [{"app": r["name"], "assigned": r["assigned"], "inactive": r["inactive"], "inactive_pct": r["inactive_pct"],
                                         "est_annual_savings_usd": None if r["savings"] is None else round(r["savings"] / 100)} for r in rows[:10]]},
            "table": table(f"Apps with licenses unused for {days}+ days",
                           [col("name", "App", "app"), col("assigned", "Licenses", "int"), col("inactive", "Unused", "int"), col("inactive_pct", "% unused", "pct"),
                            col("savings", "Est. yearly savings", "money")], rows, total=k["apps_with_opportunities"])}


# --------------------------------------------------------------------------- ex-employees
async def ex_employee_licenses(db, limit=MAX_ROWS):
    limit = clamp(limit, 1, MAX_ROWS, MAX_ROWS)
    roster_loaded = ((await db.execute(select(func.count()).select_from(EmployeeRoster))).scalar_one() or 0) > 0
    conds = [UserProfile.okta_status.in_(GONE_STATUSES)]
    if roster_loaded:
        conds.append(func.lower(User.email).not_in(select(func.lower(EmployeeRoster.email))))
    found = (await db.execute(
        select(AppUser.app_id, App.name, User.email, UserProfile.okta_status, AppUser.last_login_at)
        .select_from(AppUser).join(App, App.id == AppUser.app_id).join(User, User.id == AppUser.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(or_(*conds)).order_by(App.name, User.email).limit(5000))).all()
    per_seat = await ReclamationService(db).seat_costs()
    if not found:
        why = "" if roster_loaded else " (Upload the employee roster from an app's Users tab for a fuller check; this one only used Okta's account status.)"
        return {"headline": "No licenses are assigned to people who appear to have left." + why,
                "model_view": {"licenses": 0, "roster_loaded": roster_loaded}, "table": None}
    rows, by_app, people, savings = [], {}, set(), 0
    for app_id, name, email, status, last in found:
        gone = (status or "").upper() in GONE_STATUSES
        rows.append({"app_id": str(app_id), "name": name, "email": email, "reason": f"Okta status: {status.title()}" if gone else "Not in the employee roster",
                     "last_login": last.isoformat() if last else None})
        by_app[name] = by_app.get(name, 0) + 1
        people.add(email)
        if app_id in per_seat:
            savings += per_seat[app_id]
    headline = f"{len(rows):,} {plural(len(rows), 'license is', 'licenses are')} assigned to {len(people):,} {plural(len(people), 'person', 'people')} who appear to have left, across {len(by_app):,} {plural(len(by_app), 'app')}"
    headline += f" (about {money(savings)} a year in seats)." if savings else "."
    headline += (" 'Not in the employee roster' can also include contractors, so check before removing access."
                 if roster_loaded else " This used Okta's account status only; upload the employee roster from an app's Users tab for a fuller check.")
    top = sorted(by_app.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {"headline": headline,
            "model_view": {"licenses": len(rows), "people": len(people), "apps": len(by_app), "roster_loaded": roster_loaded,
                           "est_annual_savings_usd": round(savings / 100), "top_apps": [{"app": n, "licenses": c} for n, c in top]},
            "table": table("Licenses assigned to people who appear to have left",
                           [col("name", "App", "app"), col("email", "Person", "text"), col("reason", "Why", "text"), col("last_login", "Last activity", "date")],
                           rows[:limit], total=len(rows))}


# --------------------------------------------------------------------------- missing contract data
async def missing_contract_data(db, limit=100):
    limit = clamp(limit, 1, 200, 100)
    year_ago = datetime.now(timezone.utc).date() - timedelta(days=365)
    users = {a: int(n or 0) for a, n in (await db.execute(select(AppUser.app_id, func.count(AppUser.id)).group_by(AppUser.app_id))).all()}
    paid = {a: int(c or 0) for a, c in (await db.execute(
        select(AppPayment.app_id, func.sum(AppPayment.amount_cents)).where(AppPayment.paid_on >= year_ago, AppPayment.currency == "USD")
        .group_by(AppPayment.app_id))).all()}
    contracts = {a: (int(n or 0), end) for a, n, end in (await db.execute(
        select(Contract.app_id, func.count(Contract.id), func.max(Contract.end_date)).group_by(Contract.app_id))).all()}
    costed = {a for (a,) in (await db.execute(select(License.app_id).where(or_(License.total_annual_cost_cents > 0, License.cost_per_seat_cents > 0)).distinct())).all()}
    apps = (await db.execute(select(App.id, App.name, App.owner_email, AppSetting.owner_email, AppSetting.business_owner)
                             .select_from(App).outerjoin(AppSetting, AppSetting.app_id == App.id))).all()
    active, rows, counts = 0, [], {"contract": 0, "renewal": 0, "cost": 0, "owner": 0}
    for app_id, name, owner, setting_owner, business_owner in apps:
        n_users, spend = users.get(app_id, 0), paid.get(app_id, 0)
        if n_users == 0 and spend == 0:
            continue
        active += 1
        gaps = []
        if app_id not in contracts:
            gaps.append("contract"); counts["contract"] += 1
        elif contracts[app_id][1] is None:
            gaps.append("renewal date"); counts["renewal"] += 1
        if app_id not in costed and spend == 0:
            gaps.append("cost"); counts["cost"] += 1
        if not any((v or "").strip() for v in (owner, setting_owner, business_owner)):
            gaps.append("owner"); counts["owner"] += 1
        if gaps:
            rows.append({"app_id": str(app_id), "name": name, "users": n_users, "spend": spend, "missing": ", ".join(gaps)})
    rows.sort(key=lambda r: (-r["spend"], -r["users"], r["name"]))
    if not rows:
        return {"headline": f"Every one of the {active:,} active apps has a contract, a renewal date, a cost and an owner.", "model_view": {"active_apps": active, "apps_missing": 0}, "table": None}
    has = lambda n: plural(n, "has", "have")
    headline = (f"{len(rows):,} of {active:,} active apps are missing contract details: {counts['contract']:,} {has(counts['contract'])} no contract, "
                f"{counts['renewal']:,} {has(counts['renewal'])} no renewal date, {counts['cost']:,} {has(counts['cost'])} no cost on file and "
                f"{counts['owner']:,} {has(counts['owner'])} no owner. The biggest spenders and busiest apps are first.")
    return {"headline": headline,
            "model_view": {"active_apps": active, "apps_missing": len(rows), "no_contract": counts["contract"], "no_renewal_date": counts["renewal"],
                           "no_cost_on_file": counts["cost"], "no_owner": counts["owner"],
                           "first_apps": [{"app": r["name"], "users": r["users"], "paid_last_12_months_usd": round(r["spend"] / 100), "missing": r["missing"]} for r in rows[:10]]},
            "table": table("Active apps with missing contract details",
                           [col("name", "App", "app"), col("users", "Users", "int"), col("spend", "Paid, last 12 months", "money"), col("missing", "Missing", "text")],
                           rows[:limit], total=len(rows))}


# --------------------------------------------------------------------------- spend
async def top_spend(db, limit=10):
    limit = clamp(limit, 1, 50, 10)
    since = (datetime.now(timezone.utc).date() - timedelta(days=365)).isoformat()
    s = await PaymentsService(db).summary({"date_from": since})
    if not s["payments_in_system"]:
        return {"headline": "No payments have been loaded yet. Upload a payments file on the Payments page and I can show where the money goes.",
                "model_view": {"payments_loaded": False}, "table": None}
    apps, k = s["apps"], s["kpis"]
    if not apps:
        return {"headline": "There were no payments in the last 12 months.", "model_view": {"payments_loaded": True, "total_usd": 0}, "table": None}
    top = apps[:limit]
    top_sum = sum(a["total_cents"] for a in top)
    pct = round(100.0 * top_sum / k["total_cents"]) if k["total_cents"] else 0
    return {"headline": f"You paid {money(k['total_cents'])} across {k['applications']:,} {plural(k['applications'], 'app')} in the last 12 months. The top {len(top)} account for {money(top_sum)} ({pct}%).",
            "model_view": {"total_usd_last_12_months": round(k["total_cents"] / 100), "ap_usd": round(k["ap_cents"] / 100), "expense_usd": round(k["expense_cents"] / 100),
                           "apps_with_payments": k["applications"], "top_apps": [{"app": a["name"], "total_usd": round(a["total_cents"] / 100)} for a in top[:10]]},
            "table": table("Spend by app, last 12 months",
                           [col("name", "App", "app"), col("total_cents", "Total", "money"), col("ap_cents", "AP", "money"), col("expense_cents", "Expense", "money"), col("last_paid", "Last payment", "date")],
                           [{"app_id": a["app_id"], "name": a["name"], "total_cents": a["total_cents"], "ap_cents": a["ap_cents"], "expense_cents": a["expense_cents"], "last_paid": a["last_paid"]} for a in top],
                           total=k["applications"])}


# --------------------------------------------------------------------------- renewals
async def upcoming_renewals(db, days=90):
    days = clamp(days, 7, 365, 90)
    today = datetime.now(timezone.utc).date()
    found = (await db.execute(
        select(Contract.app_id, App.name, Contract.end_date, Contract.total_value_cents, Contract.auto_renews, Contract.cancellation_notice_days, Contract.status,
               Contract.owner_email, App.owner_email)
        .select_from(Contract).join(App, App.id == Contract.app_id)
        .where(Contract.end_date >= today, Contract.end_date <= today + timedelta(days=days)).order_by(Contract.end_date).limit(300))).all()
    rows = []
    for app_id, name, end, value, auto, notice, status, contract_owner, app_owner in found:
        if str(getattr(status, "value", status) or "").lower() in ENDED_CONTRACT:
            continue
        rows.append({"app_id": str(app_id), "name": name, "end_date": end.isoformat(), "days_left": (end - today).days, "value": value,
                     "auto_renews": "Yes" if auto else "No", "cancel_by": (end - timedelta(days=notice)).isoformat() if notice else None,
                     "owner": contract_owner or app_owner or None})
    if not rows:
        return {"headline": f"No contracts end in the next {days} days.", "model_view": {"days": days, "renewals": 0}, "table": None}
    total = sum(r["value"] or 0 for r in rows)
    return {"headline": f"{len(rows):,} {plural(len(rows), 'contract ends', 'contracts end')} in the next {days} days" + (f", worth {money(total)}." if total else "."),
            "model_view": {"days": days, "renewals": len(rows), "total_value_usd": round(total / 100),
                           "soonest": [{"app": r["name"], "ends": r["end_date"], "days_left": r["days_left"], "auto_renews": r["auto_renews"], "cancel_by": r["cancel_by"]} for r in rows[:10]]},
            "table": table(f"Contracts ending in the next {days} days",
                           [col("name", "App", "app"), col("end_date", "Ends", "date"), col("days_left", "Days left", "int"), col("value", "Value", "money"),
                            col("auto_renews", "Auto-renews", "text"), col("cancel_by", "Cancel by", "date"), col("owner", "Owner", "text")], rows)}


# --------------------------------------------------------------------------- owners
async def apps_without_owners(db, limit=100):
    limit = clamp(limit, 1, 200, 100)
    owner = func.coalesce(func.nullif(func.trim(App.owner_email), ""), func.nullif(func.trim(AppSetting.owner_email), ""), func.nullif(func.trim(AppSetting.business_owner), ""))
    found = (await db.execute(
        select(App.id, App.name, func.count(AppUser.id)).select_from(App).outerjoin(AppSetting, AppSetting.app_id == App.id)
        .outerjoin(AppUser, AppUser.app_id == App.id).where(owner.is_(None)).group_by(App.id, App.name)
        .order_by(func.count(AppUser.id).desc(), App.name).limit(MAX_ROWS))).all()
    if not found:
        return {"headline": "Every app has an owner.", "model_view": {"apps_without_owner": 0}, "table": None}
    rows = [{"app_id": str(i), "name": n, "users": int(c or 0)} for i, n, c in found]
    capped = len(rows) >= MAX_ROWS
    return {"headline": f"{'At least ' if capped else ''}{len(rows):,} {plural(len(rows), 'app has', 'apps have')} no owner, business owner or IT owner. The busiest are first. Add owners on each app's App Info tab.",
            "model_view": {"apps_without_owner": len(rows), "at_least": capped, "busiest": [{"app": r["name"], "users": r["users"]} for r in rows[:15]]},
            "table": table("Apps without an owner", [col("name", "App", "app"), col("users", "Users", "int")], rows[:limit], total=len(rows))}



# =========================================================================== more reports (the rest of the prompt library)
def _val(x) -> str:
    return str(getattr(x, "value", x) or "").lower()


def _month_start(today: date, back: int) -> date:
    y, m = today.year, today.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


async def _users_and_spend(db, since):
    """Assigned people per app, and USD paid per app since `since`."""
    users = {a: int(n or 0) for a, n in (await db.execute(select(AppUser.app_id, func.count(AppUser.id)).group_by(AppUser.app_id))).all()}
    paid = {a: int(c or 0) for a, c in (await db.execute(
        select(AppPayment.app_id, func.sum(AppPayment.amount_cents)).where(AppPayment.paid_on >= since, AppPayment.currency == "USD").group_by(AppPayment.app_id))).all()}
    return users, paid


async def shadow_it(db, limit=100):
    limit = clamp(limit, 1, 200, 100)
    users, paid = await _users_and_spend(db, datetime.now(timezone.utc).date() - timedelta(days=365))
    apps = (await db.execute(select(App.id, App.name, App.is_shadow_it, App.status))).all()
    rows, flagged, no_sso = [], 0, 0
    for app_id, name, shadow, status in apps:
        n, spend = users.get(app_id, 0), paid.get(app_id, 0)
        if n == 0 and spend == 0:
            continue                                                  # not in use
        why = []
        st = _val(status)
        if shadow:
            why.append("Marked as shadow IT in Tab")
        elif st and st not in ("managed", "sanctioned"):
            why.append(f"Status: {st.replace('_', ' ')}")
        if why:
            flagged += 1
        if n == 0 and spend > 0:
            why.append("Paid for, but nobody is assigned through Okta")
            no_sso += 1
        if why:
            rows.append({"app_id": str(app_id), "name": name, "users": n, "spend": spend, "why": "; ".join(why)})
    rows.sort(key=lambda r: (-r["spend"], -r["users"], r["name"]))
    if not rows:
        return {"headline": "Nothing in use looks like shadow IT: every app with users or payments is managed or sanctioned, and every app you pay for has people assigned in Okta.",
                "model_view": {"shadow_it_apps": 0}, "table": None}
    return {"headline": f"{len(rows):,} {plural(len(rows), 'app looks', 'apps look')} like shadow IT: {flagged:,} flagged unmanaged or shadow IT in Tab, and {no_sso:,} {plural(no_sso, 'is', 'are')} paid for but not assigned to anyone through Okta. "
                        "This is based on what Tab knows (Okta, the payments you've loaded, and the status on each app).",
            "model_view": {"shadow_it_apps": len(rows), "flagged_in_tab": flagged, "paid_but_not_in_okta": no_sso,
                           "first_apps": [{"app": r["name"], "users": r["users"], "paid_last_12_months_usd": round(r["spend"] / 100), "why": r["why"]} for r in rows[:10]]},
            "table": table("Apps that look like shadow IT", [col("name", "App", "app"), col("users", "Users", "int"), col("spend", "Paid, last 12 months", "money"), col("why", "Why", "text")], rows[:limit], total=len(rows))}


async def new_apps(db, days=90, limit=100):
    days, limit = clamp(days, 7, 365, 90), clamp(limit, 1, 200, 100)
    now = datetime.now(timezone.utc)
    total_apps = int((await db.execute(select(func.count(App.id)))).scalar_one() or 0)
    first_day = func.date(App.first_seen_at)
    top = (await db.execute(select(first_day, func.count(App.id)).group_by(first_day).order_by(func.count(App.id).desc()).limit(1))).first()
    initial = detect_initial_import(top[0] if top else None, int(top[1]) if top else 0, total_apps)
    conds = [App.first_seen_at >= now - timedelta(days=days)]
    if initial is not None:
        conds.append(first_day != initial)
    found = (await db.execute(select(App.id, App.name, App.first_seen_at, App.discovered_via).where(*conds).order_by(App.first_seen_at.desc()).limit(MAX_ROWS))).all()
    if not found:
        return {"headline": f"No new apps appeared in the last {days} days." + (" (Apps first seen when Tab was set up are not counted as new.)" if initial else ""),
                "model_view": {"new_apps": 0, "days": days}, "table": None}
    spend = {a: int(c or 0) for a, c in (await db.execute(
        select(AppPayment.app_id, func.sum(AppPayment.amount_cents)).where(AppPayment.app_id.in_([r[0] for r in found]), AppPayment.paid_on >= now.date() - timedelta(days=365),
                                                                            AppPayment.currency == "USD").group_by(AppPayment.app_id))).all()}
    rows = [{"app_id": str(i), "name": n, "first_seen": f.isoformat() if f else None, "source": (s or "unknown").replace("_", " ").title(), "annual": spend.get(i, 0)} for i, n, f, s in found]
    return {"headline": f"{len(rows):,} {plural(len(rows), 'app was', 'apps were')} first seen in the last {days} days" + (f" (not counting the apps first seen on {initial.isoformat()}, when Tab was set up)." if initial else "."),
            "model_view": {"new_apps": len(rows), "days": days, "newest": [{"app": r["name"], "source": r["source"], "paid_last_12_months_usd": round(r["annual"] / 100)} for r in rows[:10]]},
            "table": table(f"Apps first seen in the last {days} days", [col("name", "App", "app"), col("first_seen", "First seen", "date"), col("source", "Source", "text"), col("annual", "Paid, last 12 months", "money")], rows[:limit], total=len(rows))}


async def zombie_apps(db, limit=100):
    limit = clamp(limit, 1, 200, 100)
    today = datetime.now(timezone.utc).date()
    by_app = defaultdict(list)
    for app_id, status, end in (await db.execute(select(Contract.app_id, Contract.status, Contract.end_date))).all():
        by_app[app_id].append((_val(status) in ENDED_CONTRACT or (end is not None and end < today), end))
    ended = {a: max(e for _, e in cs if e) for a, cs in by_app.items() if all(done for done, _ in cs) and any(e for _, e in cs)}
    zombies = []
    if ended:
        grace = timedelta(days=30)                                    # a final invoice just after the end date isn't a zombie
        since = min(ended.values()) + grace
        paid = defaultdict(list)
        for app_id, paid_on, cents in (await db.execute(select(AppPayment.app_id, AppPayment.paid_on, AppPayment.amount_cents)
                                                       .where(AppPayment.app_id.in_(list(ended)), AppPayment.currency == "USD", AppPayment.paid_on >= since))).all():
            if paid_on > ended[app_id] + grace:
                paid[app_id].append((paid_on, int(cents or 0)))
        zombies = [(a, ps) for a, ps in paid.items() if sum(c for _, c in ps) > 0]
    if not zombies:
        return {"headline": "No apps are being paid after their contract ended.", "model_view": {"zombie_apps": 0}, "table": None}
    names = dict((await db.execute(select(App.id, App.name).where(App.id.in_([a for a, _ in zombies])))).all())
    rows = sorted(({"app_id": str(a), "name": names.get(a, "Unknown app"), "ended": ended[a].isoformat(), "paid_since": sum(c for _, c in ps), "payments": len(ps),
                    "last_paid": max(d for d, _ in ps).isoformat()} for a, ps in zombies), key=lambda r: (-r["paid_since"], r["name"]))
    total = sum(r["paid_since"] for r in rows)
    return {"headline": f"{len(rows):,} {plural(len(rows), 'app has', 'apps have')} no live contract but {plural(len(rows), 'is', 'are')} still being paid: {money(total)} since their contracts ended. Worth checking whether these were cancelled in the vendor's system.",
            "model_view": {"zombie_apps": len(rows), "paid_since_contract_end_usd": round(total / 100),
                           "top_apps": [{"app": r["name"], "ended": r["ended"], "paid_since_usd": round(r["paid_since"] / 100)} for r in rows[:10]]},
            "table": table("Apps still being paid after their contract ended",
                           [col("name", "App", "app"), col("ended", "Contract ended", "date"), col("paid_since", "Paid since", "money"), col("payments", "Payments", "int"), col("last_paid", "Last payment", "date")], rows[:limit], total=len(rows))}


async def owner_review(db, limit=100):
    limit = clamp(limit, 1, 200, 100)
    apps = (await db.execute(select(App.id, App.name, App.owner_email, AppSetting.owner_email, AppSetting.business_owner).select_from(App)
                             .outerjoin(AppSetting, AppSetting.app_id == App.id))).all()
    users = {a: int(n or 0) for a, n in (await db.execute(select(AppUser.app_id, func.count(AppUser.id)).group_by(AppUser.app_id))).all()}
    owners = {}
    for app_id, name, owner, setting_owner, business in apps:
        mail = next((v.strip() for v in (owner, setting_owner, business) if v and v.strip()), None)
        owners[app_id] = mail
    emails = sorted({m.lower() for m in owners.values() if m})
    gone = set()
    roster_loaded = ((await db.execute(select(func.count()).select_from(EmployeeRoster))).scalar_one() or 0) > 0
    if emails:
        gone = {e.lower() for (e,) in (await db.execute(select(User.email).select_from(User).join(UserProfile, UserProfile.user_id == User.id)
                                                        .where(func.lower(User.email).in_(emails), UserProfile.okta_status.in_(GONE_STATUSES)))).all()}
        if roster_loaded:
            on_roster = {e.lower() for (e,) in (await db.execute(select(EmployeeRoster.email).where(func.lower(EmployeeRoster.email).in_(emails)))).all()}
            gone |= {e for e in emails if e not in on_roster}
    suggest = {}
    for app_id, mail in (await db.execute(select(Contract.app_id, Contract.owner_email).where(Contract.owner_email.is_not(None)))).all():
        if mail and mail.strip() and mail.strip().lower() not in gone:
            suggest.setdefault(app_id, mail.strip())
    rows, missing, stale = [], 0, 0
    for app_id, name, *_ in apps:
        mail, n = owners.get(app_id), users.get(app_id, 0)
        if mail is None:
            if n == 0:
                continue
            issue, missing = "No owner", missing + 1
        elif mail.lower() in gone:
            issue, stale = "Owner appears to have left" if not roster_loaded else "Owner left or isn't in the HR roster", stale + 1
        else:
            continue
        rows.append({"app_id": str(app_id), "name": name, "users": n, "issue": issue, "owner": mail, "suggested": suggest.get(app_id)})
    rows.sort(key=lambda r: (-r["users"], r["name"]))
    if not rows:
        return {"headline": "Every app in use has an owner who still appears to be here.", "model_view": {"missing": 0, "stale": 0}, "table": None}
    with_suggestion = sum(1 for r in rows if r["suggested"])
    return {"headline": f"{len(rows):,} {plural(len(rows), 'app needs', 'apps need')} an owner update: {missing:,} {plural(missing, 'has', 'have')} no owner and {stale:,} {plural(stale, 'has', 'have')} an owner who appears to have left. "
                        f"{with_suggestion:,} {plural(with_suggestion, 'has', 'have')} a contract owner who could take over. The busiest apps are first.",
            "model_view": {"apps_needing_owner_update": len(rows), "no_owner": missing, "owner_left": stale, "with_suggested_owner": with_suggestion, "busiest": [{"app": r["name"], "users": r["users"], "issue": r["issue"]} for r in rows[:10]]},
            "table": table("Apps that need an owner update", [col("name", "App", "app"), col("users", "Users", "int"), col("issue", "Issue", "text"), col("owner", "Current owner", "text"), col("suggested", "Suggested owner", "text")], rows[:limit], total=len(rows))}


async def auto_renewals(db, days=180, limit=100):
    days, limit = clamp(days, 30, 730, 180), clamp(limit, 1, 200, 100)
    today = datetime.now(timezone.utc).date()
    found = (await db.execute(
        select(Contract.app_id, App.name, Contract.end_date, Contract.total_value_cents, Contract.cancellation_notice_days, Contract.status, Contract.owner_email, App.owner_email)
        .select_from(Contract).join(App, App.id == Contract.app_id)
        .where(Contract.auto_renews.is_(True), Contract.end_date >= today - timedelta(days=60), Contract.end_date <= today + timedelta(days=days)).order_by(Contract.end_date).limit(300))).all()
    rows, soon, passed, nonotice = [], 0, 0, 0
    for app_id, name, end, value, notice, status, c_owner, a_owner in found:
        if _val(status) in ENDED_CONTRACT:
            continue
        cancel_by = end - timedelta(days=notice) if notice else None
        if cancel_by is None:
            state, nonotice = "No notice period on file", nonotice + 1
        elif cancel_by < today:
            state, passed = "Cancel-by date has passed", passed + 1
        elif (cancel_by - today).days <= 30:
            state, soon = f"Act within {(cancel_by - today).days} days", soon + 1
        else:
            state = "OK for now"
        rows.append({"app_id": str(app_id), "name": name, "end_date": end.isoformat(), "cancel_by": cancel_by.isoformat() if cancel_by else None, "state": state, "value": value, "owner": c_owner or a_owner or None,
                     "_sort": (cancel_by or end + timedelta(days=3650))})
    rows.sort(key=lambda r: (r["_sort"], r["name"]))
    for r in rows:
        r.pop("_sort")
    if not rows:
        return {"headline": f"No auto-renewing contracts end in the next {days} days.", "model_view": {"auto_renewals": 0, "days": days}, "table": None}
    total = sum(r["value"] or 0 for r in rows)
    headline = f"{len(rows):,} auto-renewing {plural(len(rows), 'contract ends', 'contracts end')} within {days} days" + (f", worth {money(total)}" if total else "") + f". {soon:,} must be cancelled within 30 days, {passed:,} {plural(passed, 'is', 'are')} already past the cancel-by date"
    headline += f", and {nonotice:,} {plural(nonotice, 'has', 'have')} no notice period on file." if nonotice else "."
    return {"headline": headline,
            "model_view": {"auto_renewals": len(rows), "days": days, "total_value_usd": round(total / 100), "cancel_within_30_days": soon, "cancel_date_passed": passed, "no_notice_period": nonotice,
                           "most_urgent": [{"app": r["name"], "ends": r["end_date"], "cancel_by": r["cancel_by"], "state": r["state"]} for r in rows[:10]]},
            "table": table(f"Auto-renewing contracts ending in the next {days} days", [col("name", "App", "app"), col("end_date", "Ends", "date"), col("cancel_by", "Cancel by", "date"), col("state", "Status", "text"), col("value", "Value", "money"), col("owner", "Owner", "text")], rows[:limit], total=len(rows))}


async def apps_without_contracts(db, limit=100):
    limit = clamp(limit, 1, 200, 100)
    today = datetime.now(timezone.utc).date()
    users, paid = await _users_and_spend(db, today - timedelta(days=365))
    by_app = defaultdict(list)
    for app_id, status, end in (await db.execute(select(Contract.app_id, Contract.status, Contract.end_date))).all():
        by_app[app_id].append((_val(status) in ENDED_CONTRACT or (end is not None and end < today), end))
    names = dict((await db.execute(select(App.id, App.name))).all())
    rows, none_on_file, only_ended = [], 0, 0
    for app_id, name in names.items():
        n, spend = users.get(app_id, 0), paid.get(app_id, 0)
        if n == 0 and spend == 0:
            continue
        cs = by_app.get(app_id)
        if not cs:
            issue, none_on_file = "No contract on file", none_on_file + 1
        elif all(done for done, _ in cs):
            last = max((e for _, e in cs if e), default=None)
            issue, only_ended = f"Only ended contracts{f' (last ended {last.isoformat()})' if last else ''}", only_ended + 1
        else:
            continue
        rows.append({"app_id": str(app_id), "name": name, "users": n, "spend": spend, "issue": issue})
    rows.sort(key=lambda r: (-r["spend"], -r["users"], r["name"]))
    if not rows:
        return {"headline": "Every active app has a live contract on file.", "model_view": {"apps_without_contract": 0}, "table": None}
    return {"headline": f"{len(rows):,} active {plural(len(rows), 'app has', 'apps have')} no live contract: {none_on_file:,} {plural(none_on_file, 'has', 'have')} none on file and {only_ended:,} {plural(only_ended, 'has', 'have')} only expired or cancelled ones. The biggest spenders and busiest apps are first.",
            "model_view": {"apps_without_contract": len(rows), "none_on_file": none_on_file, "only_ended_contracts": only_ended,
                           "first_apps": [{"app": r["name"], "users": r["users"], "paid_last_12_months_usd": round(r["spend"] / 100), "issue": r["issue"]} for r in rows[:10]]},
            "table": table("Active apps without a live contract", [col("name", "App", "app"), col("users", "Users", "int"), col("spend", "Paid, last 12 months", "money"), col("issue", "Issue", "text")], rows[:limit], total=len(rows))}


async def license_position(db, app=None, limit=100):
    limit = clamp(limit, 1, 200, 100)
    needle = str(app or "").strip().lower()[:100]
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    bought = {a: (int(s or 0), int(c or 0)) for a, s, c in (await db.execute(
        select(License.app_id, func.sum(License.seats_purchased), func.sum(License.total_annual_cost_cents)).group_by(License.app_id))).all() if s}
    use = {a: (int(n or 0), int(act or 0)) for a, n, act in (await db.execute(
        select(AppUser.app_id, func.count(AppUser.id), func.sum(case((AppUser.last_login_at >= cutoff, 1), else_=0))).group_by(AppUser.app_id))).all()}
    names = dict((await db.execute(select(App.id, App.name))).all())
    counted = (await ReclamationService(db).counted_apps())["counted"]
    rows, unassigned_total, over_total = [], 0, 0
    for app_id, (seats, cost) in bought.items():
        name = names.get(app_id)
        if not name or (needle and needle not in name.lower()):
            continue
        assigned, active = use.get(app_id, (0, 0))
        known = app_id in counted
        unassigned, over = max(seats - assigned, 0), max(assigned - seats, 0)
        unassigned_total += unassigned
        over_total += over
        rows.append({"app_id": str(app_id), "name": name, "purchased": seats, "assigned": assigned, "active": active if known else None, "unassigned": unassigned, "over": over,
                     "utilization": round(100.0 * active / seats, 1) if known and seats else None})
    rows.sort(key=lambda r: (-(r["unassigned"] + r["over"]), r["name"]))
    if not rows:
        return {"headline": (f"I couldn't find seat counts on file for an app matching “{app}”." if needle else "No apps have purchased seat counts on file yet. Add them on an app's License tab."),
                "model_view": {"apps_with_seat_counts": 0}, "table": None}
    return {"headline": f"{len(rows):,} {plural(len(rows), 'app has', 'apps have')} seat counts on file: {unassigned_total:,} purchased seats aren't assigned to anyone, and {over_total:,} people are assigned beyond what was bought. "
                        "Active means a sign-in in the last 60 days, and is shown only where Tab has a verified activity source.",
            "model_view": {"apps_with_seat_counts": len(rows), "unassigned_seats": unassigned_total, "over_assigned": over_total,
                           "first_apps": [{"app": r["name"], "purchased": r["purchased"], "assigned": r["assigned"], "active": r["active"], "utilization_pct": r["utilization"]} for r in rows[:10]]},
            "table": table("License position by app", [col("name", "App", "app"), col("purchased", "Purchased", "int"), col("assigned", "Assigned", "int"), col("active", "Active (60d)", "int"),
                                                       col("unassigned", "Unassigned seats", "int"), col("over", "Over-assigned", "int"), col("utilization", "Utilization", "pct")], rows[:limit], total=len(rows))}


async def reclaim_candidates(db, days=60, app=None, limit=200):
    days, limit = clamp(days, 14, 90, 60), clamp(limit, 1, MAX_ROWS, 200)
    needle = str(app or "").strip()[:100]
    app_id = None
    if needle:
        app_id = (await db.execute(select(App.id).where(App.name.icontains(needle, autoescape=True)).order_by(App.name).limit(1))).scalar_one_or_none()
        if app_id is None:
            return {"headline": f"I couldn't find an app called “{needle}”.", "model_view": {"found": False}, "table": None}
    res = await ReclamationService(db).inactive(days, app_id=str(app_id) if app_id else None, limit=limit)
    if not res.get("ready"):
        return {"headline": "There isn't enough verified sign-in data yet to say who is idle. Connect an activity source, or mark an app as trusted on the Reclamation page.", "model_view": {"ready": False}, "table": None}
    if not res["rows"]:
        return {"headline": f"No one has been idle for {days}+ days" + (f" on {needle}." if needle else " on the apps with verified activity."), "model_view": {"idle_licenses": 0, "days": days}, "table": None}
    rows = [{"app_id": r["app_id"], "name": r["app"], "email": r["email"], "last_active": r["last_active"], "days_inactive": r["days_inactive"], "license": r["license"],
             "savings": r["est_annual_savings_cents"]} for r in res["rows"]]
    per_app = defaultdict(int)
    for r in rows:
        per_app[r["name"]] += 1
    savings = sum(r["savings"] or 0 for r in rows)
    return {"headline": f"{res['total']:,} {plural(res['total'], 'license has', 'licenses have')} had no sign-in for {days}+ days" + (f" on {needle}" if needle else "") + ", the most idle first"
                        + (f" (the {len(rows):,} listed would save about {money(savings)} a year)." if savings else "."),
            "model_view": {"idle_licenses": res["total"], "days": days, "listed": len(rows), "est_annual_savings_usd_of_listed": round(savings / 100),
                           "by_app": [{"app": n, "listed": c} for n, c in sorted(per_app.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]},
            "table": table(f"Idle licenses ({days}+ days)", [col("name", "App", "app"), col("email", "Person", "text"), col("last_active", "Last activity", "date"), col("days_inactive", "Days idle", "int"),
                                                              col("license", "License", "text"), col("savings", "Est. yearly savings", "money")], rows, total=res["total"])}


async def spend_spikes(db, limit=25):
    limit = clamp(limit, 1, 100, 25)
    today = datetime.now(timezone.utc).date()
    this_month, last, prev = _month_start(today, 0), _month_start(today, 1), _month_start(today, 2)
    month = func.date_trunc("month", AppPayment.paid_on)
    found = (await db.execute(select(AppPayment.app_id, month, func.sum(AppPayment.amount_cents)).where(AppPayment.paid_on >= prev, AppPayment.paid_on < this_month, AppPayment.currency == "USD")
                              .group_by(AppPayment.app_id, month))).all()
    if not found:
        return {"headline": "There are no payments in the last two full months to compare. Upload payments on the Payments page first.", "model_view": {"payments_in_window": False}, "table": None}
    by_app = defaultdict(lambda: {"prev": 0, "last": 0})
    for app_id, m, cents in found:
        by_app[app_id]["last" if (m.year, m.month) == (last.year, last.month) else "prev"] += int(cents or 0)
    spikes = []
    for app_id, v in by_app.items():
        change = v["last"] - v["prev"]
        pct = round(100.0 * change / v["prev"], 1) if v["prev"] > 0 else None
        if change >= 100_000 and (pct is None or pct >= 25):
            spikes.append((app_id, v["prev"], v["last"], change, pct))
    label = last.strftime("%B %Y")
    if not spikes:
        return {"headline": f"No app's spend jumped noticeably in {label} compared with the month before (a rise of at least $1,000 and 25%).", "model_view": {"spikes": 0, "month": label}, "table": None}
    spikes.sort(key=lambda s: (-s[3]))
    names = dict((await db.execute(select(App.id, App.name).where(App.id.in_([s[0] for s in spikes])))).all())
    rows = [{"app_id": str(a), "name": names.get(a, "Unknown app"), "previous": p, "last": l, "change": c, "pct": pct} for a, p, l, c, pct in spikes]
    total = sum(r["change"] for r in rows)
    return {"headline": f"{len(rows):,} {plural(len(rows), 'app spent', 'apps spent')} noticeably more in {label} than the month before, {money(total)} more in total.",
            "model_view": {"spikes": len(rows), "month": label, "total_increase_usd": round(total / 100),
                           "biggest": [{"app": r["name"], "previous_usd": round(r["previous"] / 100), "last_usd": round(r["last"] / 100), "pct": r["pct"]} for r in rows[:10]]},
            "table": table(f"Spend increases in {label}", [col("name", "App", "app"), col("previous", "Month before", "money"), col("last", label, "money"), col("change", "Change", "money"), col("pct", "% change", "pct")], rows[:limit], total=len(rows))}


async def cost_per_user(db, limit=25):
    limit = clamp(limit, 1, 100, 25)
    since = datetime.now(timezone.utc).date() - timedelta(days=365)
    paid = {a: int(c or 0) for a, c in (await db.execute(select(AppPayment.app_id, func.sum(AppPayment.amount_cents)).where(AppPayment.paid_on >= since, AppPayment.currency == "USD")
                                                         .group_by(AppPayment.app_id))).all()}
    if not paid:
        return {"headline": "No payments in the last 12 months, so there's no cost to divide yet. Upload payments on the Payments page first.", "model_view": {"payments_loaded": False}, "table": None}
    dept = func.coalesce(func.nullif(UserProfile.department, ""), func.nullif(User.department, ""), "Unknown")
    per_app_dept = (await db.execute(select(AppUser.app_id, dept, func.count(AppUser.id)).select_from(AppUser).join(User, User.id == AppUser.user_id)
                                     .outerjoin(UserProfile, UserProfile.user_id == User.id).group_by(AppUser.app_id, dept))).all()
    headcount = {d: int(n or 0) for d, n in (await db.execute(select(dept, func.count(func.distinct(User.id))).select_from(AppUser).join(User, User.id == AppUser.user_id)
                                                              .outerjoin(UserProfile, UserProfile.user_id == User.id).group_by(dept))).all()}
    people = int((await db.execute(select(func.count(func.distinct(AppUser.user_id))))).scalar_one() or 0)
    users_in_app = defaultdict(int)
    for app_id, d, n in per_app_dept:
        users_in_app[app_id] += int(n or 0)
    alloc, allocated = defaultdict(float), 0
    for app_id, d, n in per_app_dept:                                  # an app's spend is shared among the people assigned to it
        if app_id in paid and users_in_app[app_id]:
            share = paid[app_id] * int(n or 0) / users_in_app[app_id]
            alloc[d] += share
            allocated += share
    total = sum(paid.values())
    if not people or not allocated:
        return {"headline": f"You paid {money(total)} in the last 12 months, but none of the apps you pay for have people assigned, so I can't work out a cost per person.", "model_view": {"total_usd": round(total / 100), "people": people}, "table": None}
    rows = sorted(({"name": d, "people": headcount.get(d, 0), "allocated": round(a), "per_person": round(a / headcount[d]) if headcount.get(d) else None} for d, a in alloc.items()), key=lambda r: (-r["allocated"], r["name"]))
    org_pp = round(allocated / people)
    unallocated = max(total - allocated, 0)
    return {"headline": f"About {money(org_pp)} a person over the last 12 months ({money(allocated)} across {people:,} {plural(people, 'person', 'people')}). Each app's spend is shared among the people assigned to it"
                        + (f"; {money(unallocated)} of payments are for apps nobody is assigned to, and aren't included." if unallocated > 100 else "."),
            "model_view": {"org_cost_per_person_usd": round(org_pp / 100), "people": people, "allocated_usd": round(allocated / 100), "unallocated_usd": round(unallocated / 100),
                           "top_departments": [{"department": r["name"], "people": r["people"], "allocated_usd": round(r["allocated"] / 100), "per_person_usd": None if r["per_person"] is None else round(r["per_person"] / 100)} for r in rows[:10]]},
            "table": table("SaaS cost per person, by department", [col("name", "Department", "text"), col("people", "People", "int"), col("allocated", "Spend allocated", "money"), col("per_person", "Cost per person", "money")], rows[:limit], total=len(rows))}

async def overlapping_apps(db, limit=25):
    limit = clamp(limit, 1, 100, 25)
    today = datetime.now(timezone.utc).date()
    labelled = (await db.execute(select(AppSetting.app_functions, App.id, App.name).select_from(AppSetting).join(App, App.id == AppSetting.app_id)
                                 .where(AppSetting.app_functions.is_not(None)))).all()
    members, display, with_function = defaultdict(dict), {}, {}
    for fns, app_id, name in labelled:                                 # an app can have several functions, and counts under each
        names = [f for f in (fns or []) if f]
        if not names:
            continue
        with_function[app_id] = name
        for f in names:
            display.setdefault(f.lower(), f)
            members[f.lower()][app_id] = name
    if not with_function:
        return {"headline": "No apps have a function yet (what each app is for, like “Video conferencing”), so I can't tell which tools overlap. Import your categories first: "
                            "a Zylo export with a Functions column works.", "model_view": {"functions_known": False}, "table": None,
                "action": {"label": "Import categories", "page": "categories"}}
    users, paid = await _users_and_spend(db, today - timedelta(days=365))
    owned = defaultdict(set)                                           # person -> their apps (among the apps that have a function)
    for user_id, app_id in (await db.execute(select(AppUser.user_id, AppUser.app_id).where(AppUser.app_id.in_(list(with_function))))).all():
        owned[user_id].add(app_id)
    rows, in_overlap, overlapping_people = [], set(), set()
    for key, mem in members.items():
        active = {a: n for a, n in mem.items() if users.get(a, 0) > 0 or paid.get(a, 0) > 0}      # only tools actually in use can be redundant
        if len(active) < 2:
            continue
        ids = set(active)
        both = {u for u, apps in owned.items() if len(apps & ids) >= 2}
        in_overlap |= ids
        overlapping_people |= both
        names = sorted(active.values())
        rows.append({"name": display[key], "apps": len(active), "app_names": ", ".join(names[:5]) + (f" +{len(names) - 5} more" if len(names) > 5 else ""),
                     "licenses": sum(users.get(a, 0) for a in ids), "overlap_people": len(both), "spend": sum(paid.get(a, 0) for a in ids), "_names": names})
    rows.sort(key=lambda r: (-r["spend"], -r["apps"], r["name"]))
    functions_known = len(members)
    if not rows:
        return {"headline": f"No two apps in use share a function. {len(with_function):,} {plural(len(with_function), 'app has', 'apps have')} a function recorded, across {functions_known:,} {plural(functions_known, 'function')}.",
                "model_view": {"overlapping_functions": 0, "apps_with_function": len(with_function)}, "table": None}
    spend = sum(paid.get(a, 0) for a in in_overlap)
    return {"headline": f"{len(rows):,} {plural(len(rows), 'function is', 'functions are')} covered by more than one app ({len(in_overlap):,} apps in all), and {len(overlapping_people):,} {plural(len(overlapping_people), 'person holds', 'people hold')} licenses for two or more apps doing the same job. "
                        f"Those apps cost about {money(spend)} over the last 12 months. Only apps with a function recorded are compared ({len(with_function):,} so far).",
            "model_view": {"overlapping_functions": len(rows), "apps_in_overlap": len(in_overlap), "people_with_overlapping_licenses": len(overlapping_people), "paid_last_12_months_usd": round(spend / 100),
                           "apps_with_function": len(with_function),
                           "functions": [{"function": r["name"], "apps": r["_names"][:8], "licenses": r["licenses"], "people_with_2_or_more": r["overlap_people"], "paid_last_12_months_usd": round(r["spend"] / 100)} for r in rows[:10]]},
            "table": table("Functions covered by more than one app",
                           [col("name", "Function", "text"), col("apps", "Apps", "int"), col("app_names", "Which apps", "text"), col("licenses", "Licenses", "int"),
                            col("overlap_people", "People with 2+ of them", "int"), col("spend", "Paid, last 12 months", "money")],
                           [{k: v for k, v in r.items() if k != "_names"} for r in rows[:limit]], total=len(rows))}


# --------------------------------------------------------------------------- the list the assistant (and the page) work from
def _schema(**props):
    return {"type": "object", "properties": props, "required": []}


TOOLS = {
    "underutilized_apps": {"fn": underutilized_apps, "label": "Unused licenses", "args": ("days", "limit"),
                           "description": "Rank apps by licenses with no sign-in for a number of days, with estimated yearly savings. Only apps whose activity is verified are counted.",
                           "schema": _schema(days={"type": "integer", "description": "Days without sign-in, 14 to 90 (default 60)"}, limit={"type": "integer", "description": "How many apps to list (default 25)"})},
    "ex_employee_licenses": {"fn": ex_employee_licenses, "label": "Ex-employee licenses", "args": ("limit",),
                             "description": "Find licenses still assigned to people who appear to have left (Okta says deprovisioned/suspended, or not in the uploaded HR roster).",
                             "schema": _schema(limit={"type": "integer", "description": "Maximum people to list"})},
    "missing_contract_data": {"fn": missing_contract_data, "label": "Missing contract data", "args": ("limit",),
                              "description": "List active apps that are missing a contract, a renewal date, a cost on file or an owner, biggest spenders first.",
                              "schema": _schema(limit={"type": "integer", "description": "How many apps to list (default 100)"})},
    "top_spend": {"fn": top_spend, "label": "Spend by app", "args": ("limit",),
                  "description": "Where the money goes: total payments by app over the last 12 months (needs payments to have been loaded).",
                  "schema": _schema(limit={"type": "integer", "description": "How many apps to list (default 10)"})},
    "upcoming_renewals": {"fn": upcoming_renewals, "label": "Upcoming renewals", "args": ("days",),
                          "description": "Contracts that end in the next N days, with value, auto-renew and cancel-by dates.",
                          "schema": _schema(days={"type": "integer", "description": "Look-ahead in days, 7 to 365 (default 90)"})},
    "shadow_it": {"fn": shadow_it, "label": "Shadow IT", "args": ("limit",),
                  "description": "Find apps in use that look unmanaged: flagged shadow IT or unmanaged in Tab, or paid for but with nobody assigned through Okta.",
                  "schema": _schema(limit={"type": "integer", "description": "How many apps to list"})},
    "new_apps": {"fn": new_apps, "label": "New apps", "args": ("days", "limit"),
                 "description": "Apps Tab first discovered in the last N days (apps first seen at initial setup are excluded), with source and spend.",
                 "schema": _schema(days={"type": "integer", "description": "Look-back in days, 7 to 365 (default 90)"}, limit={"type": "integer", "description": "How many apps to list"})},
    "zombie_apps": {"fn": zombie_apps, "label": "Zombie apps", "args": ("limit",),
                    "description": "Apps whose contracts have all ended or been cancelled but which are still being paid.",
                    "schema": _schema(limit={"type": "integer", "description": "How many apps to list"})},
    "owner_review": {"fn": owner_review, "label": "App owner review", "args": ("limit",),
                     "description": "Apps in use with no owner, or whose owner appears to have left, with a suggested replacement from the contract owner where there is one.",
                     "schema": _schema(limit={"type": "integer", "description": "How many apps to list"})},
    "auto_renewals": {"fn": auto_renewals, "label": "Auto-renewing contracts", "args": ("days", "limit"),
                      "description": "Auto-renewing contracts ending in the next N days, with cancel-by dates and whether the notice window is open, closing or already passed.",
                      "schema": _schema(days={"type": "integer", "description": "Look-ahead in days, 30 to 730 (default 180)"}, limit={"type": "integer", "description": "How many contracts to list"})},
    "apps_without_contracts": {"fn": apps_without_contracts, "label": "Apps without contracts", "args": ("limit",),
                               "description": "Active apps (users assigned or paid in the last 12 months) with no contract on file, or only ended ones.",
                               "schema": _schema(limit={"type": "integer", "description": "How many apps to list"})},
    "license_position": {"fn": license_position, "label": "License position", "args": ("app", "limit"),
                         "description": "Compare seats purchased with seats assigned and actively used, per app. Pass app to focus on one vendor by name.",
                         "schema": _schema(app={"type": "string", "description": "Part of an app's name, e.g. 'zoom'"}, limit={"type": "integer", "description": "How many apps to list"})},
    "reclaim_candidates": {"fn": reclaim_candidates, "label": "Idle licenses", "args": ("days", "app", "limit"),
                           "description": "List the people whose licenses have had no sign-in for N days, most idle first, with estimated savings. Pass app to focus on one app by name.",
                           "schema": _schema(days={"type": "integer", "description": "Days without sign-in, 14 to 90 (default 60)"}, app={"type": "string", "description": "Part of an app's name"}, limit={"type": "integer", "description": "How many people to list"})},
    "spend_spikes": {"fn": spend_spikes, "label": "Spend spikes", "args": ("limit",),
                     "description": "Apps whose spend rose noticeably in the last full month compared with the month before.",
                     "schema": _schema(limit={"type": "integer", "description": "How many apps to list"})},
    "cost_per_user": {"fn": cost_per_user, "label": "Cost per user", "args": ("limit",),
                      "description": "SaaS spend per person over the last 12 months, overall and by department (each app's spend is shared among the people assigned to it).",
                      "schema": _schema(limit={"type": "integer", "description": "How many departments to list"})},
    "overlapping_apps": {"fn": overlapping_apps, "label": "Overlapping apps", "args": ("limit",),
                         "description": "Find functions (what apps are for, e.g. video conferencing) covered by more than one app in use, with spend and the people holding licenses for several of them. Needs apps to have a function recorded.",
                         "schema": _schema(limit={"type": "integer", "description": "How many functions to list"})},
    "apps_without_owners": {"fn": apps_without_owners, "label": "Apps without owners", "args": ("limit",),
                            "description": "List apps that have no owner, business owner or IT owner, busiest first.",
                            "schema": _schema(limit={"type": "integer", "description": "How many apps to list (default 100)"})},
}


async def run_tool(db, name, args=None) -> dict:
    """Run one tool by name. Unknown names and bad arguments are refused; a failure becomes a plain message, never an exception."""
    spec = TOOLS.get(name)
    if spec is None:
        return {"headline": "I don't have a report called that.", "model_view": {"error": "unknown tool"}, "table": None, "tool": name, "label": name, "ok": False}
    clean = {k: v for k, v in (args or {}).items() if k in spec["args"]} if isinstance(args, dict) else {}
    try:
        out = await spec["fn"](db, **clean)
    except Exception:
        return {"headline": "I couldn't read that data just now. Please try again in a moment.", "model_view": {"error": "lookup failed"}, "table": None,
                "tool": name, "label": spec["label"], "ok": False}
    return {**out, "tool": name, "label": spec["label"], "ok": True}


# --------------------------------------------------------------------------- understanding a question without AI
ROUTES = (
    ("ex_employee_licenses", ("ex-employee", "ex employee", "former employee", "left the company", "departed", "offboard", "terminated", "no longer employed")),
    ("shadow_it", ("shadow it", "shadow-it", "unsanctioned", "unmanaged app", "rogue app")),
    ("overlapping_apps", ("overlap", "redundan", "duplicate tool", "duplicate app", "same function", "do the same job", "doing the same")),
    ("zombie_apps", ("zombie", "cancelled but", "canceled but", "still paying", "still incurring", "still being paid", "after cancel")),
    ("new_apps", ("new app", "newly discovered", "recently discovered", "recently added", "added in the last", "just discovered")),
    ("owner_review", ("update app owner", "stale owner", "owner review", "missing or stale", "owner has left", "owners who left")),
    ("apps_without_contracts", ("without contract", "no contract", "contract records", "missing contract record")),
    ("missing_contract_data", ("missing contract", "contract data", "contract gap", "missing renewal", "missing data", "complete contract")),
    ("auto_renewals", ("auto-renew", "auto renew", "autorenew", "notice period", "notice window", "cancel-by", "cancel by")),
    ("upcoming_renewals", ("renew", "expir", "contract end", "coming due")),
    ("apps_without_owners", ("owner", "ownerless", "nobody owns")),
    ("license_position", ("license position", "effective license", "seats purchased", "purchased seats", "contracted licenses", "seat count")),
    ("reclaim_candidates", ("reclaim unused", "idle user", "idle license", "hasn't signed in", "haven't signed in", "has not signed in", "have not signed in", "not signed in")),
    ("spend_spikes", ("spike", "month-over-month", "month over month", "spending more", "jump in spend", "increase in spend", "spend increase")),
    ("cost_per_user", ("cost per user", "per person", "per employee", "per head", "per user")),
    ("top_spend", ("spend", "spending", "paid", "payment", "cost", "money", "expensive", "budget")),
    ("underutilized_apps", ("underutil", "unused", "inactive", "idle", "wasted", "shelfware", "not using", "savings", "reclaim", "licenses we don't use")),
)


def route_question(text: str):
    """(tool name, arguments) for a plain-English question, or None. Used when no AI is connected."""
    t = " ".join(str(text or "").lower().split())
    for tool, words in ROUTES:
        if any(w in t for w in words):
            days = re.search(r"(\d{1,3})\s*(?:days?|d)\b", t)
            return tool, ({"days": int(days.group(1))} if days and tool in ("underutilized_apps", "upcoming_renewals", "auto_renewals", "new_apps", "reclaim_candidates") else {})
    return None
