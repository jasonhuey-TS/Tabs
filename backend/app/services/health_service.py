"""Portfolio data health: how complete the information about your apps is, and so how far to trust the savings and spend numbers.

Each check asks one question of the apps it applies to ("does it have an owner?", "does it have a contract?") and reports how many say yes,
with the apps that don't, biggest first, and where to go to fix them. The score weighs the checks by how much they matter to the numbers.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import App, AppUser, Contract
from app.models.app_extras import AppPayment, AppSetting, DiscoveredApp, EmployeeRoster, ExternalLink
from app.models.connector_config import ConnectorConfig
from app.services.reclamation_service import IN_FORCE, ReclamationService

SAMPLE = 8
STALE_DAYS = 3
GOOD, FAIR = 0.9, 0.6
CONNECTOR_NAMES = {"okta_activity": "Okta sign-ins", "zylo": "Zylo", "app_discovery": "App discovery", "zoom": "Zoom", "slack": "Slack", "google_workspace": "Google Workspace",
                   "microsoft365": "Microsoft 365", "salesforce": "Salesforce", "claude": "Claude"}

#        id, label, weight, who it applies to, why it matters, where to fix it
CHECKS = [
    ("owner", "An owner", 20, "apps in use", "Someone to ask before licenses are reclaimed or a contract renews.", {"label": "Add owners", "page": "apps"}),
    ("activity", "Reliable activity data", 20, "apps with people assigned", "Without it Tab can't tell who is idle, so those apps are left out of the savings.", {"label": "Connect an activity source", "page": "integration-library"}),
    ("price", "A price per license", 20, "apps with people assigned", "Without it an app's savings can't be put in dollars.", {"label": "Add a contract or payments", "page": "payments"}),
    ("contract", "A contract on file", 15, "apps you pay for", "Gives the renewal date and cancel-by deadline that decide when a saving can start.", {"label": "Add contracts", "page": "contracts"}),
    ("spend", "Spend on record", 10, "apps with people assigned", "Needed to price licenses. Free tools will show here too.", {"label": "Add payments", "page": "payments"}),
    ("contract_details", "Contract end date and notice period", 5, "apps with a contract", "Without them the cancel-by deadline can't be worked out.", {"label": "Complete the contracts", "page": "contracts"}),
    ("category", "A category", 5, "apps in use", "Groups apps for analysis and spotting overlap.", {"label": "Set categories", "page": "categories"}),
    ("functions", "A function", 5, "apps in use", "Says what the app is for, so overlapping tools can be found.", {"label": "Set functions", "page": "categories"}),
]


def band(pct):
    return "good" if pct >= GOOD else "fair" if pct >= FAIR else "poor"


def grade(score):
    return "Strong" if score >= 85 else "Fair" if score >= 65 else "Needs work"


class HealthService:
    def __init__(self, db):
        self.db = db

    async def _evaluate(self):
        """Who each check applies to and who passes it, plus the facts about the apps."""
        today = datetime.now(timezone.utc).date()
        info = {i: {"app_id": str(i), "name": n, "category": getattr(c, "value", c), "owner": o} for i, n, c, o in (await self.db.execute(select(App.id, App.name, App.category, App.owner_email))).all()}
        users = {a: int(n or 0) for a, n in (await self.db.execute(select(AppUser.app_id, func.count(AppUser.id)).group_by(AppUser.app_id))).all()}
        spend = {a: int(t or 0) for a, t in (await self.db.execute(
            select(AppPayment.app_id, func.sum(AppPayment.amount_cents)).where(AppPayment.currency == "USD", AppPayment.amount_cents > 0, AppPayment.paid_on >= today - timedelta(days=365))
            .group_by(AppPayment.app_id))).all()}
        settings = {a: (o, b, f) for a, o, b, f in (await self.db.execute(select(AppSetting.app_id, AppSetting.owner_email, AppSetting.business_owner, AppSetting.app_functions))).all()}
        in_force, complete = set(), set()
        for a, status, start, end, notice in (await self.db.execute(select(Contract.app_id, Contract.status, Contract.start_date, Contract.end_date, Contract.cancellation_notice_days))).all():
            if getattr(status, "value", status) in IN_FORCE and (start is None or start <= today) and (end is None or end >= today):
                in_force.add(a)
                if end is not None and notice:
                    complete.add(a)
        recl = ReclamationService(self.db)
        priced, counted = set(await recl.seat_costs()), set((await recl.counted_apps())["counted"])

        rows = {}
        for app_id, i in info.items():
            u, s = users.get(app_id, 0), spend.get(app_id, 0)
            o, b, f = settings.get(app_id, (None, None, None))
            rows[app_id] = {**i, "users": u, "spend_cents": s, "in_use": u > 0 or s > 0, "has_users": u > 0, "paid": s > 0, "owner_ok": bool(i["owner"] or o or b),
                            "contract": app_id in in_force, "complete": app_id in complete, "priced": app_id in priced, "counted": app_id in counted,
                            "category_ok": i["category"] not in (None, "other"), "functions_ok": bool(f)}
        rules = {"owner": ("in_use", "owner_ok"), "activity": ("has_users", "counted"), "price": ("has_users", "priced"), "contract": ("paid", "contract"), "spend": ("has_users", "paid"),
                 "contract_details": ("contract", "complete"), "category": ("in_use", "category_ok"), "functions": ("in_use", "functions_ok")}
        return rows, rules, {"priced": priced, "counted": counted, "any_payments": bool(spend), "any_contracts": bool(in_force)}

    @staticmethod
    def _missing(rows, rules, check_id):
        applies, passes = rules[check_id]
        eligible = [r for r in rows.values() if r[applies]]
        miss = sorted((r for r in eligible if not r[passes]), key=lambda r: (-r["users"], -r["spend_cents"], r["name"].lower()))
        return len(eligible), miss

    async def overview(self) -> dict:
        rows, rules, facts = await self._evaluate()
        checks, weighted, weights = [], 0.0, 0
        for cid, label, weight, applies, why, fix in CHECKS:
            total, miss = self._missing(rows, rules, cid)
            ok = total - len(miss)
            pct = ok / total if total else None
            if pct is not None:
                weighted, weights = weighted + weight * pct, weights + weight
            checks.append({"id": cid, "label": label, "weight": weight, "applies_to": applies, "why": why, "fix": fix, "ok": ok, "total": total,
                           "pct": None if pct is None else round(100 * pct), "status": None if pct is None else band(pct), "missing_count": len(miss),
                           "missing": [{"app_id": r["app_id"], "name": r["name"], "users": r["users"], "spend_cents": r["spend_cents"]} for r in miss[:SAMPLE]]})
        score = round(100 * weighted / weights) if weights else None
        fix_first = sorted((c for c in checks if c["pct"] is not None and c["pct"] < 100 * GOOD), key=lambda c: -c["weight"] * (1 - c["pct"] / 100))[:3]

        trust = {"ready": False}
        recl = ReclamationService(self.db)
        k = (await recl.overview(60)).get("kpis")
        if k:
            by, total = k.get("savings_by_basis") or {}, k.get("est_annual_savings_cents") or 0
            trust = {"ready": True, "est_annual_savings_cents": total, "reliable_pct": round(100 * (by.get("license", 0) + by.get("contract", 0)) / total) if total else None,
                     "rough_cents": k.get("low_confidence_savings_cents") or 0, "unpriced_apps": k.get("apps_missing_cost") or 0, "apps_counted": k.get("apps_counted") or 0}

        roster = int((await self.db.execute(select(func.count()).select_from(EmployeeRoster))).scalar_one() or 0) > 0
        zylo_unmatched = int((await self.db.execute(select(func.count()).select_from(ExternalLink).where(ExternalLink.source == "zylo", ExternalLink.kind == "application", ExternalLink.status == "unmatched"))).scalar_one() or 0)
        shadow = int((await self.db.execute(select(func.count()).select_from(DiscoveredApp).where(DiscoveredApp.status == "new", DiscoveredApp.active == True))).scalar_one() or 0)   # noqa: E712
        now = datetime.now(timezone.utc)
        syncs = []
        for key, last, status in (await self.db.execute(select(ConnectorConfig.key, ConnectorConfig.last_sync_at, ConnectorConfig.sync_status))).all():
            if last is None and status is None:
                continue
            age = (now - (last if last.tzinfo else last.replace(tzinfo=timezone.utc))).days if last else None
            syncs.append({"key": key, "name": CONNECTOR_NAMES.get(key, key.replace("_", " ").title()), "last_sync_at": last.isoformat() if last else None, "age_days": age,
                          "status": "error" if status == "error" else "never" if last is None else "stale" if age > STALE_DAYS else "ok"})
        syncs.sort(key=lambda s: ({"error": 0, "never": 1, "stale": 2, "ok": 3}[s["status"]], s["name"]))
        setup = [{"id": "roster", "label": "HR roster uploaded", "ok": roster, "why": "Lets Tab spot licenses held by people who've left.", "fix": {"label": "Upload the roster", "page": "apps"}},
                 {"id": "payments", "label": "Payments loaded", "ok": facts["any_payments"], "why": "Spend is what prices a license.", "fix": {"label": "Add payments", "page": "payments"}},
                 {"id": "contracts", "label": "Contracts loaded", "ok": facts["any_contracts"], "why": "Renewal dates decide when a saving can start.", "fix": {"label": "Add contracts", "page": "contracts"}},
                 {"id": "activity", "label": "An activity source connected", "ok": bool(facts["counted"]), "why": "Tab can only judge who is idle where activity is reliable.", "fix": {"label": "Open the Integration Library", "page": "integration-library"}}]
        in_use = [r for r in rows.values() if r["in_use"]]
        return {"score": score, "grade": grade(score) if score is not None else None, "total_apps": len(rows), "in_use_apps": len(in_use), "paid_apps": sum(1 for r in in_use if r["paid"]),
                "checks": checks, "fix_first": [{"id": c["id"], "label": c["label"], "missing_count": c["missing_count"], "pct": c["pct"], "fix": c["fix"]} for c in fix_first],
                "savings_trust": trust, "setup": setup, "pending": {"zylo_unmatched": zylo_unmatched, "shadow_review": shadow}, "syncs": syncs}

    async def missing(self, check_id, limit=200) -> dict | None:
        """Every app that fails one check, biggest first."""
        if check_id not in {c[0] for c in CHECKS}:
            return None
        rows, rules, _ = await self._evaluate()
        total, miss = self._missing(rows, rules, check_id)
        limit = max(1, min(int(limit or 200), 500))
        return {"check": check_id, "total": total, "missing_count": len(miss), "rows": [{"app_id": r["app_id"], "name": r["name"], "users": r["users"], "spend_cents": r["spend_cents"]} for r in miss[:limit]]}
