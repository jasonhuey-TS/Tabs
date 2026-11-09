"""Append a line to an app's history. Best effort: history must never break the thing it describes."""
from app.models.app_extras import AppEvent


async def record_event(db, app_id, kind: str, detail: str) -> None:
    try:
        async with db.begin_nested():
            db.add(AppEvent(app_id=app_id, kind=kind[:40], detail=(detail or "")[:2000]))
    except Exception:
        pass
