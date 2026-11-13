"""What an app-discovery sync writes into Tab.

Rules that keep it safe to run every night:
  - Decisions are never undone: an app you ignored, approved or added stays that way, whatever the next sync finds.
  - An app Tab already has is recognised by name and marked 'known', not offered as new.
  - Apps nobody has authorized any more are kept but marked inactive, so history isn't lost.
"""
import uuid
from collections import Counter

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import App, AppUser, User
from app.models.app_extras import AppAlias, DiscoveredApp, DiscoveredAppUser

CHUNK = 500
ADDED = ("added", "approved")


def _unique(rows, *keys):
    """Postgres refuses an upsert that names the same row twice in one statement: keep the last of each."""
    return list({tuple(r[k] for k in keys): r for r in rows}.values())


async def name_index(db):
    """A function that says which Tab app a name belongs to: a saved alias, then the same name or vendor. Ambiguous names match nothing."""
    from app.services.payment_import import normalize_vendor
    by_name, ambiguous = {}, set()
    for app_id, name, vendor in (await db.execute(select(App.id, App.name, App.vendor))).all():
        for label in (name, vendor):
            key = normalize_vendor(label)
            if key:
                if key in by_name and by_name[key] != str(app_id):
                    ambiguous.add(key)
                by_name[key] = str(app_id)
    aliases = {a: str(i) for a, i in (await db.execute(select(AppAlias.alias, AppAlias.app_id))).all()}

    def find(*names):
        for name in names:
            key = normalize_vendor(name)
            if key:
                hit = aliases.get(key) or (by_name.get(key) if key not in ambiguous else None)
                if hit:
                    return hit
        return None
    return find


async def attach_people(db, app_id, emails) -> int:
    """Make the people who authorized an app show up as its users in Tab (only people Tab already knows; nobody is removed)."""
    emails = sorted({str(e).strip().lower() for e in emails if e})
    if not emails:
        return 0
    users = {}
    for i in range(0, len(emails), CHUNK):
        for uid, email in (await db.execute(select(User.id, User.email).where(User.email.in_(emails[i:i + CHUNK])))).all():
            users[str(email).lower()] = uid
    have = {str(u) for (u,) in (await db.execute(select(AppUser.user_id).where(AppUser.app_id == app_id))).all()}
    rows = [{"app_id": app_id, "user_id": uid, "role_in_app": "Connected to work account"} for uid in users.values() if str(uid) not in have]
    for i in range(0, len(rows), CHUNK):
        await db.execute(pg_insert(AppUser).values(rows[i:i + CHUNK]).on_conflict_do_nothing())
    return len(rows)


async def apply_source(db, source, records, run_at) -> dict:
    """Store what one source found, keeping every earlier decision. Returns counts for the sync message."""
    existing = {str(e): (st, app) for e, st, app in (await db.execute(
        select(DiscoveredApp.external_id, DiscoveredApp.status, DiscoveredApp.app_id).where(DiscoveredApp.source == source))).all()}
    find = await name_index(db)
    out, rows, people, linked = Counter(), [], [], []
    for r in records:
        eid = str(r["external_id"])
        status, app_id = existing.get(eid, (None, None))
        if status in (None, "new"):
            match = find(r["name"], r.get("publisher"))
            status, app_id = ("known", uuid.UUID(match)) if match else ("new", None)
            if eid not in existing and not match:
                out["found_new"] += 1
        out["found"] += 1
        rows.append({"source": source, "external_id": eid, "name": r["name"][:255], "publisher": (r.get("publisher") or None), "kind": r.get("kind") or "web", "scopes": r["scopes"],
                     "risk": r["risk"], "highlights": r["highlights"], "user_count": len(r["users"]), "all_users": bool(r.get("all_users")), "status": status, "app_id": app_id,
                     "active": True, "homepage": r.get("homepage"), "first_seen_at": run_at, "last_seen_at": run_at})
        people.extend({"source": source, "external_id": eid, "email": e} for e in r["users"])
        if status in ADDED and app_id:
            linked.append((app_id, r["users"]))
    rows = _unique(rows, "source", "external_id")
    cols = ("name", "publisher", "kind", "scopes", "risk", "highlights", "user_count", "all_users", "status", "app_id", "active", "homepage", "last_seen_at")
    for i in range(0, len(rows), CHUNK):
        stmt = pg_insert(DiscoveredApp).values(rows[i:i + CHUNK])
        await db.execute(stmt.on_conflict_do_update(index_elements=["source", "external_id"], set_={c: getattr(stmt.excluded, c) for c in cols}))
    await db.execute(update(DiscoveredApp).where(DiscoveredApp.source == source, DiscoveredApp.last_seen_at < run_at).values(active=False))      # nobody has these authorized now
    await db.execute(delete(DiscoveredAppUser).where(DiscoveredAppUser.source == source))
    people = _unique(people, "source", "external_id", "email")
    for i in range(0, len(people), CHUNK):
        await db.execute(pg_insert(DiscoveredAppUser).values(people[i:i + CHUNK]).on_conflict_do_nothing())
    for app_id, emails in linked:                                                                                                       # apps already added to Tab keep their people current
        out["people_added"] += await attach_people(db, app_id, emails)
    return {"found": out["found"], "found_new": out["found_new"], "people_added": out["people_added"]}
