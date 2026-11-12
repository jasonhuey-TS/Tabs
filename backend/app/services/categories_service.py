"""App categories and functions: a summary of coverage, a CSV of the current labels, and importing labels from another tool's export."""
from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import App, AppCategory
from app.models.app_extras import AppAlias, AppSetting
from app.services import category_import as ci
from app.services import payment_import as pi
from app.services.app_events import record_event
from app.services.reclamation_service import parse_uuid, to_csv

MAX_IMPORT_CHARS = 15_000_000
CHUNK = 500


def _val(x) -> str:
    return str(getattr(x, "value", x) or "other").lower()


class CategoryService:
    def __init__(self, db):
        self.db = db

    async def summary(self) -> dict:
        total = int((await self.db.execute(select(func.count(App.id)))).scalar_one() or 0)
        counts = Counter()
        for category, n in (await self.db.execute(select(App.category, func.count(App.id)).group_by(App.category))).all():
            counts[_val(category)] += int(n or 0)
        functions, with_function = Counter(), 0
        for (lst,) in (await self.db.execute(select(AppSetting.app_functions).where(AppSetting.app_functions.is_not(None)))).all():
            names = [f for f in (lst or []) if f]
            with_function += 1 if names else 0
            functions.update(names)
        with_sub = int((await self.db.execute(select(func.count(AppSetting.app_id)).where(AppSetting.app_subcategory.is_not(None), AppSetting.app_subcategory != ""))).scalar_one() or 0)
        return {"total": total, "with_category": total - counts["other"], "with_subcategory": with_sub, "with_function": with_function,
                "by_category": [{"category": c, "label": ci.LABELS[c], "count": counts[c]} for c in ci.CATEGORIES],
                "top_functions": [{"function": f, "apps": n} for f, n in sorted(functions.items(), key=lambda kv: (-kv[1], kv[0]))[:15]]}

    async def export_csv(self) -> str:
        rows = (await self.db.execute(select(App.name, App.vendor, App.category, AppSetting.app_subcategory, AppSetting.app_functions).select_from(App)
                                      .outerjoin(AppSetting, AppSetting.app_id == App.id).order_by(App.name))).all()
        data = [{"name": n, "vendor": v, "category": ci.LABELS.get(_val(c), "Other"), "subcategory": sub or "", "functions": "; ".join(f or [])} for n, v, c, sub, f in rows]
        return to_csv(data, [("name", "Application"), ("vendor", "Vendor"), ("category", "Category"), ("subcategory", "Subcategory"), ("functions", "Functions")])

    # ------------------------------------------------------------------ importing
    async def _plan(self, text, mapping, value_map, decisions, overwrite):
        if len(text or "") > MAX_IMPORT_CHARS:
            return None, {"error": "That file is too large (15 MB maximum)."}
        headers, rows = pi.parse_csv(text)
        if not headers:
            return None, {"error": "That file is empty or isn't a CSV."}
        if not rows:
            return None, {"error": "The file has a header row but no apps."}
        chosen = {f: h for f, h in (mapping or {}).items() if f in ("name", "category", "subcategory", "function") and h in headers} if mapping else ci.detect_columns(headers)
        apps = [(str(i), n, v, _val(c), sub, list(fns or [])) for i, n, v, c, sub, fns in (await self.db.execute(
            select(App.id, App.name, App.vendor, App.category, AppSetting.app_subcategory, AppSetting.app_functions).select_from(App).outerjoin(AppSetting, AppSetting.app_id == App.id))).all()]
        aliases = {a: str(i) for a, i in (await self.db.execute(select(AppAlias.alias, AppAlias.app_id))).all()}
        ids = {a[0] for a in apps}
        clean_decisions = {k: v for k, v in (decisions or {}).items() if v == "skip" or v in ids}
        clean_values = {str(k): (v if v in ci.CATEGORIES else "") for k, v in (value_map or {}).items()}
        plan = ci.plan_categories(rows, chosen, apps, aliases, clean_decisions, clean_values, bool(overwrite))
        return {"headers": headers, "rows": rows, "mapping": chosen, "plan": plan, "decisions": clean_decisions}, None

    async def preview(self, text, mapping=None, value_map=None, decisions=None, overwrite=False) -> dict:
        ctx, error = await self._plan(text, mapping, value_map, decisions, overwrite)
        if error:
            return error
        plan = ctx["plan"]
        base = {"headers": ctx["headers"], "mapping": ctx["mapping"], "sample": ctx["rows"][:5], "total_rows": len(ctx["rows"])}
        if plan["error"]:
            return {**base, "error": plan["error"]}
        return {**base, "error": None, "value_sources": plan["value_sources"], "values": plan["values"], "categories": [{"value": c, "label": ci.LABELS[c]} for c in ci.CATEGORIES],
                "will_update": len(plan["updates"]), "category_changes": sum(1 for u in plan["updates"] if u["category"]), "subcategory_changes": sum(1 for u in plan["updates"] if u["subcategory"]),
                "function_changes": sum(1 for u in plan["updates"] if u["functions"]),
                "unchanged": plan["unchanged"], "blank": plan["blank"], "duplicates": plan["duplicates"], "skipped": plan["skipped"], "unmatched": plan["unmatched"],
                "unmatched_rows": sum(u["rows"] for u in plan["unmatched"]),
                "examples": [{"name": u["name"], "category": ci.LABELS.get(u["category"]) if u["category"] else None, "subcategory": u["subcategory"], "functions": u["functions"]} for u in plan["updates"][:8]]}

    async def commit(self, text, mapping=None, value_map=None, decisions=None, overwrite=False, file_name="upload.csv") -> dict:
        ctx, error = await self._plan(text, mapping, value_map, decisions, overwrite)
        if error:
            return {"ok": False, **error}
        plan = ctx["plan"]
        if plan["error"]:
            return {"ok": False, "error": plan["error"]}
        for vendor, app_id in ctx["decisions"].items():                    # remember the matches you chose, for next time
            key = pi.normalize_vendor(vendor)
            if app_id == "skip" or not key:
                continue
            row = (await self.db.execute(select(AppAlias).where(AppAlias.alias == key))).scalar_one_or_none()
            if row is None:
                self.db.add(AppAlias(alias=key, app_id=parse_uuid(app_id)))
            else:
                row.app_id = parse_uuid(app_id)
        by_category = {}
        for u in plan["updates"]:
            if u["category"]:
                by_category.setdefault(u["category"], []).append(parse_uuid(u["app_id"]))
        for category, ids in by_category.items():
            for i in range(0, len(ids), CHUNK):
                await self.db.execute(update(App).where(App.id.in_(ids[i:i + CHUNK])).values(category=AppCategory(category)))
        for field, label in (("functions", "app_functions"), ("subcategory", "app_subcategory")):          # one upsert per field: each only touches its own column
            batch = [{"app_id": parse_uuid(u["app_id"]), label: u[field]} for u in plan["updates"] if u[field]]
            for i in range(0, len(batch), CHUNK):
                stmt = pg_insert(AppSetting).values(batch[i:i + CHUNK])
                await self.db.execute(stmt.on_conflict_do_update(index_elements=["app_id"], set_={label: getattr(stmt.excluded, label)}))
        for u in plan["updates"][:CHUNK]:
            bits = ([f"category set to {ci.LABELS[u['category']]}"] if u["category"] else []) + ([f"subcategory set to {u['subcategory']}"] if u["subcategory"] else []) \
                + ([f"functions set to {', '.join(u['functions'])}"] if u["functions"] else [])
            await record_event(self.db, parse_uuid(u["app_id"]), "category", f"Imported from {str(file_name)[:80]}: {'; '.join(bits)}")
        await self.db.commit()
        return {"ok": True, "error": None, "updated": len(plan["updates"]), "category_changes": sum(len(v) for v in by_category.values()), "subcategory_changes": sum(1 for u in plan["updates"] if u["subcategory"]), "function_changes": sum(1 for u in plan["updates"] if u["functions"]),
                "unchanged": plan["unchanged"], "unmatched_rows": sum(u["rows"] for u in plan["unmatched"]), "skipped": plan["skipped"], "blank": plan["blank"]}
