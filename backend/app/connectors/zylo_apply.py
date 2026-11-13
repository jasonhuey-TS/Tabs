"""What a Zylo sync writes into Tab: which Zylo app is which Tab app, categories and owners, contracts, and payments.

Rules that keep it safe to run every night:
  - Nothing a person typed into Tab is overwritten: categories, owners and so on are only filled where Tab has nothing.
  - Records are matched by their Zylo id (remembered in external_links), so a sync updates instead of duplicating.
  - Contracts already in Tab with the same app and dates are adopted, not duplicated.
"""
import uuid
from collections import Counter, defaultdict

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import App, AppCategory, Contract, ContractStatus
from app.models.app_extras import AppAlias, AppPayment, AppSetting, ExternalLink

from .zylo_map import clean, contract_fields, fingerprint, function_names, payment_fields

SOURCE = "zylo"
CHUNK = 500
MAX_EVENTS = 500


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _unique(rows, *keys):
    """Postgres refuses an upsert that names the same row twice in one statement: keep the last of each."""
    return list({tuple(r[k] for k in keys): r for r in rows}.values())


async def _upsert_links(db, rows, with_fingerprint=False):
    rows = _unique(rows, "source", "kind", "external_id")
    cols = ["local_id", "status", "label"] + (["fingerprint"] if with_fingerprint else [])
    for i in range(0, len(rows), CHUNK):
        stmt = pg_insert(ExternalLink).values(rows[i:i + CHUNK])
        await db.execute(stmt.on_conflict_do_update(index_elements=["source", "kind", "external_id"], set_={c: getattr(stmt.excluded, c) for c in cols}))


# ------------------------------------------------------------------------------------------------ apps
async def match_apps(db, zapps) -> dict:
    """Work out which Tab app each Zylo app is: a match made before, then a saved alias, then the same name. The rest are listed as unmatched."""
    from app.services.payment_import import normalize_vendor
    rows = (await db.execute(select(App.id, App.name, App.vendor))).all()
    valid, by_name, ambiguous = {str(i) for i, *_ in rows}, {}, set()
    for app_id, name, vendor in rows:
        for label in (name, vendor):
            key = normalize_vendor(label)
            if key:
                if key in by_name and by_name[key] != str(app_id):
                    ambiguous.add(key)                                    # two Tab apps share this name: never guess
                by_name[key] = str(app_id)
    aliases = {a: str(i) for a, i in (await db.execute(select(AppAlias.alias, AppAlias.app_id))).all()}
    links = {str(e): (st, str(loc) if loc else None) for e, st, loc in (await db.execute(
        select(ExternalLink.external_id, ExternalLink.status, ExternalLink.local_id)
        .where(ExternalLink.source == SOURCE, ExternalLink.kind == "application"))).all()}

    app_map, new_links, counts = {}, [], Counter()
    for za in zapps:
        zid = str(za.get("id") or "")
        if not zid:
            continue
        label = clean(za.get("app_label") or za.get("app_name")) or zid
        status, local = links.get(zid, (None, None))
        if status == "ignored":
            counts["ignored"] += 1
            continue
        if status == "matched" and local in valid:
            app_map[zid] = local
            counts["matched"] += 1
            continue
        found = None
        for name in (za.get("app_label"), za.get("app_name")):
            key = normalize_vendor(name)
            cand = (aliases.get(key) or (by_name.get(key) if key not in ambiguous else None)) if key else None
            if cand in valid:
                found = cand
                break
        row = {"source": SOURCE, "kind": "application", "external_id": zid, "label": label}
        if found:
            app_map[zid] = found
            counts["matched"] += 1
            counts["new_matches"] += 1
            new_links.append({**row, "local_id": uuid.UUID(found), "status": "matched"})
        else:
            counts["unmatched"] += 1
            new_links.append({**row, "local_id": None, "status": "unmatched"})
    await _upsert_links(db, new_links)
    return {"app_map": app_map, "total": len(zapps), **{k: counts[k] for k in ("matched", "new_matches", "unmatched", "ignored")}}


async def apply_app_details(db, zapps, stats, app_map) -> dict:
    """Fill category, subcategory, functions, owners, department and website from Zylo, only where Tab has nothing yet."""
    from app.services.app_events import record_event
    from app.services.category_import import driving_value, suggest_category
    if not app_map:
        return {"categories_set": 0, "apps_filled": 0}
    ids = [uuid.UUID(v) for v in set(app_map.values())]
    cats = {str(i): getattr(c, "value", c) for i, c in (await db.execute(select(App.id, App.category).where(App.id.in_(ids)))).all()}
    current = {str(r[0]): r[1:] for r in (await db.execute(
        select(AppSetting.app_id, AppSetting.owner_email, AppSetting.business_owner, AppSetting.department, AppSetting.website,
               AppSetting.app_subcategory, AppSetting.app_functions).where(AppSetting.app_id.in_(ids)))).all()}
    by_zid = {str(z.get("id")): z for z in zapps}
    merged = {}                                          # Several Zylo apps can be one Tab app (a Zylo "Zoom" and "Zoom Phone"): combine them so each Tab app is written once
    for zid, app_id in app_map.items():
        za, st = by_zid.get(zid) or {}, stats.get(zid) or {}
        sub, category, functions = clean(za.get("subcategory"), 120), clean(za.get("category"), 120), function_names(st)
        driver = driving_value(sub or "", category or "", functions)
        new_cat = suggest_category(driver) if driver else "other"
        owner_e, biz, dept, site, cur_sub, cur_fn = (list(current.get(app_id) or ()) + [None] * 6)[:6]
        entry = merged.setdefault(app_id, {"cat": None, "row": {}})
        if new_cat != "other" and entry["cat"] is None:
            entry["cat"] = new_cat
        for col, value, have in (("app_subcategory", sub, cur_sub), ("app_functions", functions or None, cur_fn),
                                 ("owner_email", clean(za.get("application_owner_user_email") or za.get("it_owner_user_email")), owner_e),
                                 ("business_owner", clean(za.get("business_owner_user_email")), biz), ("department", clean(za.get("business_unit")), dept),
                                 ("website", clean(za.get("launch_url"), 512), site)):
            if not value or have:
                continue
            if col == "app_functions":
                seen, joined = set(), []
                for f in list(entry["row"].get(col, [])) + list(value):
                    if f.lower() not in seen:
                        seen.add(f.lower())
                        joined.append(f)
                entry["row"][col] = joined[:10]
            else:
                entry["row"].setdefault(col, value)           # the first Zylo app with a value wins
    cat_groups, fills, events = defaultdict(list), [], []
    for app_id, entry in merged.items():
        bits, row = [], entry["row"]
        if entry["cat"] and cats.get(app_id, "other") == "other":
            cat_groups[entry["cat"]].append(uuid.UUID(app_id))
            bits.append(f"category {entry['cat']}")
        if row:
            fills.append({"app_id": uuid.UUID(app_id), **row})
            bits += [c.replace("app_", "").replace("_", " ") for c in row]
        if bits:
            events.append((uuid.UUID(app_id), "Zylo sync filled in: " + ", ".join(bits)))
    for cat, app_ids in cat_groups.items():
        for i in range(0, len(app_ids), CHUNK):
            await db.execute(update(App).where(App.id.in_(app_ids[i:i + CHUNK])).values(category=AppCategory(cat)))
    fills = _unique(fills, "app_id")
    groups = defaultdict(list)                                           # one upsert per set of columns, each touching only its own columns
    for r in fills:
        groups[tuple(sorted(k for k in r if k != "app_id"))].append(r)
    for cols, rows in groups.items():
        for i in range(0, len(rows), CHUNK):
            stmt = pg_insert(AppSetting).values(rows[i:i + CHUNK])
            await db.execute(stmt.on_conflict_do_update(index_elements=["app_id"], set_={c: getattr(stmt.excluded, c) for c in cols}))
    for app_uuid, text in events[:MAX_EVENTS]:
        await record_event(db, app_uuid, "zylo_sync", text)
    return {"categories_set": sum(len(v) for v in cat_groups.values()), "apps_filled": len(fills)}


# -------------------------------------------------------------------------------------------- contracts
def _contract_values(f):
    return {**f, "status": ContractStatus(f["status"])}


async def apply_contracts(db, zcontracts, app_map, currency="USD") -> dict:
    """Create or refresh a Tab contract for each Zylo contract that belongs to one matched app."""
    out = Counter()
    links = {str(e): (str(loc) if loc else None, fp) for e, loc, fp in (await db.execute(
        select(ExternalLink.external_id, ExternalLink.local_id, ExternalLink.fingerprint)
        .where(ExternalLink.source == SOURCE, ExternalLink.kind == "contract"))).all()}
    app_ids = [uuid.UUID(v) for v in set(app_map.values())]
    existing = (await db.execute(select(Contract.id, Contract.app_id, Contract.start_date, Contract.end_date).where(Contract.app_id.in_(app_ids)))).all() if app_ids else []
    live = {str(i) for i, *_ in existing}
    linked_locals = {loc for loc, _ in links.values() if loc}
    adoptable = {(str(a), s, e): str(i) for i, a, s, e in existing if str(i) not in linked_locals}
    to_link = []
    for zc in zcontracts:
        zid = str(zc.get("id") or "")
        if not zid:
            continue
        zapp = zc.get("application_id")
        if not zapp:                                                      # spans several apps through line items: not imported yet
            out["skipped_several_apps" if zc.get("can_have_contract_lines") else "skipped_no_app"] += 1
            continue
        app_id = app_map.get(str(zapp))
        if not app_id:
            out["skipped_unmatched_app"] += 1
            continue
        f = contract_fields(zc, currency)
        fp = fingerprint({**f, "app": app_id})
        local, old_fp = links.get(zid, (None, None))
        label = clean(zc.get("name")) or zid
        if local and local in live:
            if old_fp == fp:
                out["unchanged"] += 1
                continue
            await db.execute(update(Contract).where(Contract.id == uuid.UUID(local)).values(**_contract_values(f)))
            out["updated"] += 1
        else:
            adopt = adoptable.pop((app_id, f["start_date"], f["end_date"]), None) if (f["start_date"] or f["end_date"]) else None
            if adopt:
                local = adopt                                             # theirs already: link it, keep what they entered
                out["adopted"] += 1
            else:
                new_id = uuid.uuid4()
                db.add(Contract(id=new_id, app_id=uuid.UUID(app_id), **_contract_values(f)))
                local = str(new_id)
                out["created"] += 1
        to_link.append({"source": SOURCE, "kind": "contract", "external_id": zid, "local_id": uuid.UUID(local), "status": "matched", "label": label[:255], "fingerprint": fp})
    await db.flush()                                                      # contracts exist before anything points at them
    await _upsert_links(db, to_link, with_fingerprint=True)
    return {k: out[k] for k in ("created", "updated", "unchanged", "adopted", "skipped_several_apps", "skipped_no_app", "skipped_unmatched_app")}


# ---------------------------------------------------------------------------------------------- payments
async def count_other_payments(db) -> int:
    """How many payments Tab already holds that did not come from this sync (uploads and manual entries)."""
    return int((await db.execute(select(func.count()).select_from(AppPayment).where(AppPayment.source != SOURCE))).scalar_one() or 0)


async def load_synced_payments(db) -> dict:
    """external id -> (row id, app id, date, cents) for the payments an earlier sync wrote."""
    return {str(e): (i, a, p, c) for i, e, a, p, c in (await db.execute(
        select(AppPayment.id, AppPayment.external_id, AppPayment.app_id, AppPayment.paid_on, AppPayment.amount_cents).where(AppPayment.source == SOURCE))).all()}


async def apply_payments_page(db, page, app_map, existing, out, batch) -> None:
    """Add new payments from one page of Zylo's list and correct ones whose amount, date or app changed. Safe to repeat."""
    new_rows, changes = [], []
    for zp in page:
        zid = str(zp.get("id") or "")
        f = payment_fields(zp)
        if not zid or f is None:
            out["skipped_unreadable"] += 1
            continue
        zapp = zp.get("application_id")
        app_id = app_map.get(str(zapp)) if zapp else None
        if not app_id:
            out["unmatched"] += 1
            out["unmatched_cents"] += f["amount_cents"]
            continue
        ext = f"zylo:{zid}"
        have = existing.get(ext)
        if have is None:
            new_rows.append({"app_id": uuid.UUID(app_id), "paid_on": f["paid_on"], "amount_cents": f["amount_cents"], "currency": "USD", "reference": f["reference"],
                             "payment_type": f["payment_type"], "source": SOURCE, "external_id": ext, "import_batch": batch})
            existing[ext] = (None, app_id, f["paid_on"], f["amount_cents"])         # a repeat later in the same run is not added twice
        else:
            row_id, old_app, old_day, old_cents = have
            if row_id is not None and (str(old_app) != app_id or old_day != f["paid_on"] or old_cents != f["amount_cents"]):
                changes.append((row_id, {"app_id": uuid.UUID(app_id), "paid_on": f["paid_on"], "amount_cents": f["amount_cents"], "payment_type": f["payment_type"], "reference": f["reference"]}))
                existing[ext] = (row_id, app_id, f["paid_on"], f["amount_cents"])
    for i in range(0, len(new_rows), CHUNK):
        await db.execute(pg_insert(AppPayment).values(new_rows[i:i + CHUNK]))
    for row_id, values in changes:
        await db.execute(update(AppPayment).where(AppPayment.id == row_id).values(**values))
    out["added"] += len(new_rows)
    out["corrected"] += len(changes)
