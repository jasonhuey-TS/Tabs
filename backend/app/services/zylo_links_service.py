"""The Zylo Sync page's matching: which Zylo apps Tab couldn't match by name, and letting a person say which Tab app each one is."""
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import App
from app.models.app_extras import AppAlias, ExternalLink
from app.services.payment_import import _similarity, normalize_vendor

SOURCE, KIND = "zylo", "application"
LIST_LIMIT = 300
MIN_SCORE = 0.55


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


class ZyloLinkService:
    def __init__(self, db):
        self.db = db

    async def overview(self, status: str = "unmatched") -> dict:
        """Counts of matched / unmatched / ignored Zylo apps, and the list for one of them with the closest Tab apps suggested."""
        status = status if status in ("unmatched", "ignored") else "unmatched"
        counts = {"matched": 0, "unmatched": 0, "ignored": 0}
        for st, n in (await self.db.execute(select(ExternalLink.status, func.count()).where(ExternalLink.source == SOURCE, ExternalLink.kind == KIND).group_by(ExternalLink.status))).all():
            if st in counts:
                counts[st] = int(n or 0)
        rows = (await self.db.execute(select(ExternalLink.external_id, ExternalLink.label).where(ExternalLink.source == SOURCE, ExternalLink.kind == KIND, ExternalLink.status == status)
                                      .order_by(ExternalLink.label).limit(LIST_LIMIT))).all()
        apps = [(str(i), n) for i, n in (await self.db.execute(select(App.id, App.name).order_by(App.name))).all()] if rows else []
        keyed = [(i, n, normalize_vendor(n)) for i, n in apps]
        items = []
        for zid, label in rows:
            key = normalize_vendor(label)
            scored = sorted(((_similarity(key, k), i, n) for i, n, k in keyed if k), reverse=True)[:3] if key else []
            items.append({"zylo_id": str(zid), "name": label or str(zid), "suggestions": [{"app_id": i, "name": n, "score": round(s, 2)} for s, i, n in scored if s >= MIN_SCORE]})
        return {"counts": counts, "status": status, "items": items, "more": max(0, counts[status] - len(items)), "apps": [{"id": i, "name": n} for i, n in apps]}

    async def _link(self, zylo_id):
        return (await self.db.execute(select(ExternalLink.label).where(ExternalLink.source == SOURCE, ExternalLink.kind == KIND, ExternalLink.external_id == str(zylo_id)))).first()

    async def match(self, zylo_id, app_id):
        """Say which Tab app a Zylo app is. Also remembered as a name match, so spend uploads recognise the same name."""
        app_uuid = _uuid(app_id)
        if app_uuid is None or (await self.db.execute(select(App.id).where(App.id == app_uuid))).scalar_one_or_none() is None:
            return False, "Pick an app from the list."
        link = await self._link(zylo_id)
        if link is None:
            return False, "That Zylo app isn't known. Run a sync first."
        await self.db.execute(update(ExternalLink).where(ExternalLink.source == SOURCE, ExternalLink.kind == KIND, ExternalLink.external_id == str(zylo_id))
                              .values(local_id=app_uuid, status="matched"))
        alias = normalize_vendor(link[0])
        if alias:
            stmt = pg_insert(AppAlias).values(alias=alias, app_id=app_uuid)
            await self.db.execute(stmt.on_conflict_do_update(index_elements=["alias"], set_={"app_id": stmt.excluded.app_id}))
        await self.db.commit()
        return True, "Matched. Its category, contracts and spend arrive on the next sync."

    async def set_status(self, zylo_id, status: str):
        """'ignored' (leave this Zylo app out) or 'unmatched' (bring it back to the list)."""
        if status not in ("ignored", "unmatched") or await self._link(zylo_id) is None:
            return False, "That Zylo app isn't known."
        await self.db.execute(update(ExternalLink).where(ExternalLink.source == SOURCE, ExternalLink.kind == KIND, ExternalLink.external_id == str(zylo_id))
                              .values(status=status, local_id=None))
        await self.db.commit()
        return True, "Left out of the sync." if status == "ignored" else "Back on the list."
