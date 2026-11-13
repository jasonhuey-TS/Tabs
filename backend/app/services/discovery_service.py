"""The Shadow IT page: apps people connected to their work accounts, and deciding what to do with each."""
import re
import uuid

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.connectors import discovery_apply as da
from app.connectors import discovery_map as dm
from app.models import App, AppCategory, AppStatus
from app.models.app_extras import AppAlias, DiscoveredApp, DiscoveredAppUser
from app.services.app_events import record_event
from app.services.category_import import suggest_category
from app.services.payment_import import normalize_vendor

SOURCE_NAMES = {"google": "Google", "microsoft": "Microsoft"}
STATUS_GROUPS = {"new": ("new",), "known": ("known",), "added": ("added", "approved"), "ignored": ("ignored",)}
LIST_LIMIT = 300


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _iso(dt):
    return dt.isoformat() if dt else None


class DiscoveryService:
    def __init__(self, db):
        self.db = db

    async def overview(self, status="new", source=None, risk=None, q=None) -> dict:
        status = status if status in STATUS_GROUPS else "new"
        counts = {k: 0 for k in STATUS_GROUPS}
        for st, n in (await self.db.execute(select(DiscoveredApp.status, func.count()).where(DiscoveredApp.active == True).group_by(DiscoveredApp.status))).all():   # noqa: E712
            for group, members in STATUS_GROUPS.items():
                if st in members:
                    counts[group] += int(n or 0)
        review = {"high": 0, "medium": 0, "low": 0}
        for rk, n in (await self.db.execute(select(DiscoveredApp.risk, func.count()).where(DiscoveredApp.active == True, DiscoveredApp.status == "new").group_by(DiscoveredApp.risk))).all():   # noqa: E712
            if rk in review:
                review[rk] = int(n or 0)
        people = int((await self.db.execute(select(func.count(func.distinct(DiscoveredAppUser.email))).select_from(DiscoveredAppUser)
                                            .join(DiscoveredApp, and_(DiscoveredApp.source == DiscoveredAppUser.source, DiscoveredApp.external_id == DiscoveredAppUser.external_id)).where(DiscoveredApp.active == True, DiscoveredApp.status == "new"))).scalar_one() or 0)   # noqa: E712
        rows = (await self.db.execute(select(DiscoveredApp.source, DiscoveredApp.external_id, DiscoveredApp.name, DiscoveredApp.publisher, DiscoveredApp.kind, DiscoveredApp.risk,
                                            DiscoveredApp.highlights, DiscoveredApp.user_count, DiscoveredApp.all_users, DiscoveredApp.status, DiscoveredApp.app_id,
                                            DiscoveredApp.first_seen_at, DiscoveredApp.last_seen_at, DiscoveredApp.homepage)
                                     .where(DiscoveredApp.active == True, DiscoveredApp.status.in_(STATUS_GROUPS[status])))).all()   # noqa: E712
        needle = (q or "").strip().lower()
        picked = [r for r in rows if (not source or r[0] == source) and (not risk or r[5] == risk) and (not needle or needle in f"{r[2]} {r[3] or ''}".lower())]
        picked.sort(key=lambda r: (-dm.RANK.get(r[5], 0), -(r[7] or 0), str(r[2]).lower()))
        shown = picked[:LIST_LIMIT]
        names = {}
        linked = [r[10] for r in shown if r[10]]
        if linked:
            names = {str(i): n for i, n in (await self.db.execute(select(App.id, App.name).where(App.id.in_(linked)))).all()}
        items = [{"source": r[0], "source_name": SOURCE_NAMES.get(r[0], r[0]), "external_id": r[1], "name": r[2], "publisher": r[3], "kind": r[4], "risk": r[5], "highlights": r[6] or [],
                  "user_count": r[7] or 0, "all_users": bool(r[8]), "status": r[9], "app_id": str(r[10]) if r[10] else None, "app_name": names.get(str(r[10])) if r[10] else None,
                  "first_seen_at": _iso(r[11]), "last_seen_at": _iso(r[12]), "homepage": r[13]} for r in shown]
        apps = [{"id": str(i), "name": n} for i, n in (await self.db.execute(select(App.id, App.name).order_by(App.name))).all()] if status == "new" and shown else []
        return {"status": status, "counts": counts, "review": {**review, "people": people}, "items": items, "more": max(0, len(picked) - len(shown)), "apps": apps}

    async def people(self, source, external_id):
        row = (await self.db.execute(select(DiscoveredApp.name, DiscoveredApp.scopes, DiscoveredApp.highlights, DiscoveredApp.all_users)
                                     .where(DiscoveredApp.source == source, DiscoveredApp.external_id == external_id))).first()
        if row is None:
            return None
        emails = sorted(e for (e,) in (await self.db.execute(select(DiscoveredAppUser.email).where(DiscoveredAppUser.source == source, DiscoveredAppUser.external_id == external_id))).all())
        scopes = [{"scope": s, "label": dm.scope_label(s, source), "risk": dm.scope_risk(s, source)} for s in sorted(row[1] or [], key=lambda s: (-dm.RANK[dm.scope_risk(s, source)], s))]
        return {"name": row[0], "people": emails, "all_users": bool(row[3]), "scopes": scopes, "highlights": row[2] or []}

    async def _row(self, source, external_id):
        return (await self.db.execute(select(DiscoveredApp.name, DiscoveredApp.publisher, DiscoveredApp.status, DiscoveredApp.app_id, DiscoveredApp.homepage, DiscoveredApp.first_seen_at,
                                         DiscoveredApp.highlights, DiscoveredApp.user_count).where(DiscoveredApp.source == source, DiscoveredApp.external_id == external_id))).first()

    async def _set(self, source, external_id, **values):
        await self.db.execute(update(DiscoveredApp).where(DiscoveredApp.source == source, DiscoveredApp.external_id == external_id).values(**values))

    async def act(self, source, external_id, action, app_id=None):
        """Returns (ok, message). ignore | restore | add (as shadow IT) | approve (as a sanctioned app) | match (to an app Tab already has)."""
        row = await self._row(source, external_id)
        if row is None:
            return False, "That app isn't on the list any more. Run discovery again."
        name, publisher, status, linked, homepage, first_seen, highlights, user_count = row
        if action == "ignore":
            await self._set(source, external_id, status="ignored", app_id=None)
            await self.db.commit()
            return True, "Ignored. It won't be flagged again."
        if action == "restore":
            if status != "ignored":
                return False, "Only ignored apps can be brought back."
            await self._set(source, external_id, status="new")
            await self.db.commit()
            return True, "Back on the review list."
        if status in ("added", "approved"):
            return False, "That app is already in Tab."
        if action == "match":
            target = _uuid(app_id)
            if target is None or (await self.db.execute(select(App.id).where(App.id == target))).scalar_one_or_none() is None:
                return False, "Pick an app from the list."
            await self._set(source, external_id, status="known", app_id=target)
            alias = normalize_vendor(name)
            if alias:
                stmt = pg_insert(AppAlias).values(alias=alias, app_id=target)
                await self.db.execute(stmt.on_conflict_do_update(index_elements=["alias"], set_={"app_id": stmt.excluded.app_id}))
            await self.db.commit()
            return True, "Matched to that app. Future checks will recognise it."
        if action not in ("add", "approve"):
            return False, "Choose what to do with this app."
        existing = (await da.name_index(self.db))(name, publisher)
        if existing:                                                       # Tab already has it: link, don't duplicate
            await self._set(source, external_id, status="known", app_id=uuid.UUID(existing))
            await self.db.commit()
            return True, "Tab already has this app, so it was linked to it instead of added again."
        new_id = uuid.uuid4()
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100] or "app"
        shadow = action == "add"
        self.db.add(App(id=new_id, name=name[:255], vendor=(publisher or name)[:255], vendor_slug=slug, category=AppCategory(suggest_category(name)),
                        status=AppStatus.UNMANAGED if shadow else AppStatus.SANCTIONED, is_shadow_it=shadow, website=homepage, discovered_via=f"{source}_oauth", first_seen_at=first_seen,
                        description=f"Found in {SOURCE_NAMES.get(source, source)} account connections. Access: {'; '.join(highlights or []) or 'sign-in only'}."))
        await self.db.flush()
        emails = [e for (e,) in (await self.db.execute(select(DiscoveredAppUser.email).where(DiscoveredAppUser.source == source, DiscoveredAppUser.external_id == external_id))).all()]
        attached = await da.attach_people(self.db, new_id, emails)
        await self._set(source, external_id, status="added" if shadow else "approved", app_id=new_id)
        await record_event(self.db, new_id, "discovered", f"Found in {SOURCE_NAMES.get(source, source)} account connections ({user_count or 0} people). "
                                                          f"{'Marked as shadow IT.' if shadow else 'Approved.'}")
        await self.db.commit()
        return True, (f"Added to Tab as shadow IT with {attached} people." if shadow else f"Added to Tab as an approved app with {attached} people.")
