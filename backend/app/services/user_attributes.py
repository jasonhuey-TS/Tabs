"""Per-person values a vendor integration provides (what the Users tab can filter and show beyond Okta's own data)."""
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.app_extras import AppUserAttribute

CHUNK = 1000


async def save_attributes(db, app_id, source: str, rows) -> int:
    """rows: (user_id, {key: value}). Each sync replaces a person's values for this app; people without values are left alone."""
    rows = [(u, d) for u, d in rows if d]
    for i in range(0, len(rows), CHUNK):
        stmt = pg_insert(AppUserAttribute).values([{"app_id": app_id, "user_id": u, "source": source, "data": d} for u, d in rows[i:i + CHUNK]])
        await db.execute(stmt.on_conflict_do_update(index_elements=["app_id", "user_id"], set_={"source": stmt.excluded.source, "data": stmt.excluded.data}))
    return len(rows)


def infer_fields(rows) -> list:
    """A field list from the values alone, for when the connector that wrote them isn't available. Dates, numbers and yes/no are recognised."""
    import re
    seen = {}
    for data in rows:
        for key, value in (data or {}).items():
            if value is None:
                continue
            kind = "bool" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else \
                   "date" if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value) else "text"
            seen.setdefault(key, kind)
    return [{"key": k, "label": k.replace("_", " ").title(), "type": t} for k, t in sorted(seen.items())]
