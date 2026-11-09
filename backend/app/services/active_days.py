"""Per-person, per-app, per-day activity (what 'Days Active (of last 90)' counts)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.app_extras import UserActiveDay

CHUNK = 5000
KEEP_DAYS = 95


async def save_active_days(db, rows) -> int:
    """rows: (app_id, user_id, date). Safe to repeat: existing days are left alone."""
    unique = list(set(rows))
    for i in range(0, len(unique), CHUNK):
        values = [{"app_id": a, "user_id": u, "day": d} for a, u, d in unique[i:i + CHUNK]]
        await db.execute(pg_insert(UserActiveDay).values(values).on_conflict_do_nothing())
    return len(unique)


async def prune_active_days(db, keep_days: int = KEEP_DAYS) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).date()
    await db.execute(delete(UserActiveDay).where(UserActiveDay.day < cutoff))
