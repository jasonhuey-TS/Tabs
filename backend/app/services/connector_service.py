"""
ConnectorService - stores connector credentials and runs Integration Library syncs.

Credentials live in one encrypted JSON blob per connector (connector_configs table).
Status writes use Core UPDATE statements so nothing reads ORM attributes after a commit.
"""
from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import all_connectors, get as get_connector
from app.connectors.base import ConnectorError, as_aware, match_records
from app.core.encryption import encrypt, decrypt
from app.models import App, AppUser, User
from app.models.connector_config import ConnectorConfig
from app.services.active_days import save_active_days
from app.services.app_events import record_event

RUNNING: set = set()                      # connectors syncing inside this process
STALE_AFTER = timedelta(minutes=20)       # "running" with no progress this long = interrupted


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _load_cfg(row) -> dict:
    if not row or not row.config_encrypted:
        return {}
    try:
        return json.loads(decrypt(row.config_encrypted))
    except Exception:
        return {}


class ConnectorService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ reading

    async def _row(self, key: str):
        result = await self.db.execute(select(ConnectorConfig).where(ConnectorConfig.key == key))
        return result.scalar_one_or_none()

    async def list_state(self) -> list:
        rows = {r.key: r for r in (await self.db.execute(select(ConnectorConfig))).scalars().all()}
        target_ids = [r.target_app_id for r in rows.values() if r.target_app_id]
        names = {}
        if target_ids:
            found = await self.db.execute(select(App.id, App.name).where(App.id.in_(target_ids)))
            names = {app_id: name for app_id, name in found.all()}
        return [await self._describe(c, rows.get(c.key), names) for c in all_connectors()]

    async def describe(self, key: str) -> dict:
        c = get_connector(key)
        row = await self._row(key)
        names = {}
        if row and row.target_app_id:
            found = await self.db.execute(select(App.id, App.name).where(App.id == row.target_app_id))
            names = {app_id: name for app_id, name in found.all()}
        return await self._describe(c, row, names)

    async def _describe(self, c, row, names: dict) -> dict:
        cfg = _load_cfg(row)
        configured = await c.is_ready(self.db) if c.kind == "global" else c.is_configured(cfg)

        sync_status, sync_message = (row.sync_status if row else None), (row.last_sync_message if row else None)
        if sync_status == "running":
            beat = as_aware(row.updated_at) or as_aware(row.last_sync_started_at)
            if beat and _now() - beat > STALE_AFTER:
                sync_status = "error"
                sync_message = "The last sync was interrupted (the app restarted). Click Sync now to retry."

        if not configured:
            status = "available"
        elif sync_status == "running":
            status = "syncing"
        elif sync_status == "error":
            status = "error"
        elif row and row.last_sync_at:
            status = "connected"
        elif row and row.last_test_ok is False:
            status = "error"
        else:
            status = "configured"

        target = None
        if row and row.target_app_id:
            target = {"id": str(row.target_app_id), "name": names.get(row.target_app_id, "(app removed)")}

        return {
            "key": c.key, "name": c.name, "vendor": c.vendor, "description": c.description,
            "color": c.color, "initials": c.initials, "kind": c.kind, "provides": list(c.provides),
            "fields": [asdict(f) for f in c.fields],
            "guide": {"steps": list(c.guide.steps), "docs_url": c.guide.docs_url},
            "values": {f.key: cfg.get(f.key, "") for f in c.fields if not f.secret},
            "secrets_set": {f.key: bool(cfg.get(f.key)) for f in c.fields if f.secret},
            "configured": configured, "status": status, "target_app": target,
            "last_test": {
                "at": _iso(row.last_test_at) if row else None,
                "ok": row.last_test_ok if row else None,
                "message": row.last_test_message if row else None,
            },
            "sync": {
                "status": sync_status,
                "started_at": _iso(row.last_sync_started_at) if row else None,
                "last_at": _iso(row.last_sync_at) if row else None,
                "message": sync_message,
                "summary": (row.sync_summary or {}) if row else {},
            },
        }

    async def candidate_apps(self, key: str, q: str | None = None) -> list:
        c = get_connector(key)
        terms = [q.strip()] if q and q.strip() else list(c.app_aliases)
        if not terms:
            return []
        count = func.count(AppUser.id)
        stmt = (
            select(App.id, App.name, count)
            .outerjoin(AppUser, AppUser.app_id == App.id)
            .where(or_(*[App.name.ilike(f"%{t}%") for t in terms]))
            .group_by(App.id, App.name)
            .order_by(count.desc(), App.name)
            .limit(20)
        )
        return [{"id": str(i), "name": n, "assigned_users": int(k)} for i, n, k in (await self.db.execute(stmt)).all()]

    # ------------------------------------------------------------------ saving / testing

    async def save_config(self, key: str, values: dict, target_app_id: str | None):
        c = get_connector(key)
        row = await self._row(key)
        existing = _load_cfg(row)

        merged = {}
        for f in c.fields:
            raw = values.get(f.key)
            val = raw.strip() if isinstance(raw, str) else raw
            merged[f.key] = val or existing.get(f.key, "")      # blank secret = keep what is saved
        missing = [f.label for f in c.fields if f.required and not merged.get(f.key)]
        if missing:
            return False, "Please fill in: " + ", ".join(missing)

        target = None
        if target_app_id:
            try:
                target = uuid.UUID(target_app_id)
            except ValueError:
                return False, "That app isn't valid - pick one from the list."
            found = await self.db.execute(select(App.id).where(App.id == target))
            if found.scalar_one_or_none() is None:
                return False, "That app no longer exists - pick another."
        elif row is None or row.target_app_id is None:
            guesses = await self.candidate_apps(key)
            if guesses:
                target = uuid.UUID(guesses[0]["id"])

        if row is None:
            row = ConnectorConfig(key=key)
            self.db.add(row)
        row.config_encrypted = encrypt(json.dumps(merged))
        row.last_test_at, row.last_test_ok, row.last_test_message = None, None, None   # creds changed
        if target:
            row.target_app_id = target
        await self.db.commit()
        return True, "Saved."

    async def test(self, key: str):
        c = get_connector(key)
        row = await self._row(key)
        cfg = _load_cfg(row)
        if c.kind == "app" and not c.is_configured(cfg):
            return False, "Add your credentials first."
        try:
            message, ok = await c.test(cfg, self.db), True
        except ConnectorError as exc:
            await self.db.rollback()
            message, ok = str(exc), False
        except Exception as exc:
            await self.db.rollback()
            message, ok = f"{type(exc).__name__}: {exc}", False

        row = await self._row(key)
        if row is None:
            row = ConnectorConfig(key=key)
            self.db.add(row)
        row.last_test_at, row.last_test_ok, row.last_test_message = _now(), ok, message[:500]
        await self.db.commit()
        return ok, message

    async def disconnect(self, key: str) -> None:
        await self.db.execute(delete(ConnectorConfig).where(ConnectorConfig.key == key))
        await self.db.commit()

    # ------------------------------------------------------------------ syncing

    async def begin_sync(self, key: str):
        """Validate and mark the sync as running. Returns (status, message)."""
        c = get_connector(key)
        row = await self._row(key)
        if c.kind == "app":
            cfg = _load_cfg(row)
            if not row or not c.is_configured(cfg):
                return "blocked", "Add your credentials first."
            if not row.target_app_id:
                return "blocked", "Choose which app this connector should enrich."
        else:
            if not await c.is_ready(self.db):
                return "blocked", "Save your Okta domain and API token under Settings first."
            if row is None:
                row = ConnectorConfig(key=key)
                self.db.add(row)
                await self.db.flush()
        if key in RUNNING:
            return "running", "A sync is already running."

        await self.db.execute(update(ConnectorConfig).where(ConnectorConfig.key == key).values(
            sync_status="running", last_sync_started_at=_now(), last_sync_message="Starting..."))
        await self.db.commit()
        RUNNING.add(key)
        return "started", "Sync started."

    async def sync(self, key: str) -> None:
        """Run a sync to completion. Never raises: the outcome is written to the connector row."""
        c = get_connector(key)
        try:
            row = await self._row(key)
            cfg = _load_cfg(row)
            target_id = row.target_app_id
            state = dict(row.state or {})

            if c.kind == "global":
                async def progress(message, new_state=None):
                    values = {"last_sync_message": message[:500]}
                    if new_state is not None:
                        values["state"] = {**state, **new_state}
                    await self.db.execute(update(ConnectorConfig).where(ConnectorConfig.key == key).values(**values))
                    await self.db.commit()

                summary, new_state = await c.run(self.db, state, progress)
                await self._finish(key, True, summary.get("message", "Sync complete."), summary, {**state, **new_state})
            else:
                if not target_id:
                    raise ConnectorError("Choose which app this connector should enrich.")
                c.state_in, c.state_out = state, None
                try:
                    result = await c.fetch_users(cfg)
                    kept_state = {**state, **c.state_out} if c.state_out is not None else None
                finally:
                    c.state_in, c.state_out = None, None
                records, notes = result if isinstance(result, tuple) else (result, [])
                summary = await self._apply_records(target_id, records, c.name)
                await record_event(self.db, target_id, "connector_sync", f"{c.name} sync: {summary['message']}")
                if notes:
                    summary["notes"] = list(notes)
                    summary["message"] = f"{summary['message']} Note: {' '.join(notes)}"
                await self._finish(key, True, summary["message"], summary, kept_state)
        except Exception as exc:
            try:
                await self.db.rollback()
            except Exception:
                pass
            text = str(exc) if isinstance(exc, ConnectorError) else f"{type(exc).__name__}: {exc}"
            await self._finish(key, False, text[:500], None, None)
        finally:
            RUNNING.discard(key)

    async def _finish(self, key, ok: bool, message: str, summary, state) -> None:
        values = {"sync_status": "ok" if ok else "error", "last_sync_message": message[:500]}
        if ok:
            values["last_sync_at"] = _now()
            values["sync_summary"] = summary
        if state is not None:
            values["state"] = state
        await self.db.execute(update(ConnectorConfig).where(ConnectorConfig.key == key).values(**values))
        await self.db.commit()

    async def _apply_records(self, app_id, records, vendor: str) -> dict:
        """Write license + last-active onto people Okta already assigned to the app."""
        rows = (await self.db.execute(
            select(AppUser, User.email)
            .join(User, User.id == AppUser.user_id)
            .where(AppUser.app_id == app_id)
        )).all()
        by_email = {(email or "").strip().lower(): app_user for app_user, email in rows}

        matched, unmatched = match_records(records, set(by_email))
        day_rows = []
        for rec in matched:
            app_user = by_email[rec.email.strip().lower()]
            day_rows.extend((app_id, app_user.user_id, d) for d in (rec.active_days or ()))
            if rec.license_type:
                app_user.role_in_app = rec.license_type[:100]
            if rec.last_active_at:
                current = as_aware(app_user.last_login_at)
                if current is None or rec.last_active_at > current:
                    app_user.last_login_at = rec.last_active_at
        if day_rows:
            await save_active_days(self.db, day_rows)
        await self.db.flush()

        return {
            "vendor_accounts": len(records), "assigned_in_okta": len(by_email),
            "matched": len(matched), "unmatched": len(unmatched),
            "unmatched_sample": [r.email for r in unmatched[:25]],
            "license_counts": dict(Counter(r.license_type or "unknown" for r in matched)),
            "message": (f"Updated {len(matched):,} of {len(by_email):,} assigned users. "
                        f"{len(unmatched):,} {vendor} accounts aren't assigned to this app in Okta."),
        }

    async def sync_all_enabled(self) -> dict:
        """Used by the scheduler: run every configured, enabled connector one after another."""
        results = {}
        ordered = sorted(all_connectors(), key=lambda c: 0 if c.kind == "global" else 1)
        for c in ordered:
            row = await self._row(c.key)
            if row is not None and not row.is_enabled:
                continue
            try:
                status, message = await self.begin_sync(c.key)
                if status == "started":
                    await self.sync(c.key)
                    results[c.key] = "ok"
                elif status == "blocked":
                    continue                                    # not configured - skip silently
                else:
                    results[c.key] = status
            except Exception as exc:
                await self.db.rollback()
                results[c.key] = f"error: {exc}"
        return results
