"""Slack - account type for every person, plus real last-active dates on Enterprise Grid.

Slack's normal API has no "last active" field, and Okta can't see Slack use (people stay signed in for
months). On Enterprise Grid, admin.analytics.getFile returns one file per day for the whole organization
with an `is_active` flag per person (they posted, or read a channel or DM, that day). We read those daily
files, newest first, and keep each person's most recent active day:

  * first sync   - backfills up to 90 days (~3 seconds per day: Slack allows 20 calls a minute)
  * later syncs  - read only the days since the last sync (state is kept between syncs)

Two tokens: the bot token (xoxb-) lists people and account types; the optional analytics token (xoxp-,
a user token from an Org Owner/Admin with admin.analytics:read) supplies the activity.
If the analytics token is set and it fails, the sync FAILS rather than quietly reporting everyone as
inactive - Reclamation only trusts an app whose last sync succeeded.
"""
import asyncio
import gzip
import json
from datetime import datetime, timedelta, timezone

from .base import Connector, ConnectorError, Field, Guide, UserRecord, send
from .registry import register

API = "https://slack.com/api"
HISTORY_DAYS = 90
CALL_DELAY = 3.1                 # seconds between analytics calls (Tier 2: 20 per minute)
STOP_AFTER_MISSES = 3            # this many days in a row with no file = we've reached the start of Slack's history

# Errors that mean the token / setup is wrong, as opposed to "no file for that particular day".
FATAL = {"invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive", "missing_scope",
         "no_permission", "not_an_admin", "access_denied", "not_allowed_token_type", "org_login_required",
         "feature_not_enabled", "org_level_email_display_disabled", "team_access_not_granted"}
EXPLAIN = {
    "org_level_email_display_disabled": "Slack is hiding email addresses for the organization. Turn on email display in the "
                                        "org's admin settings, then sync again.",
    "missing_scope": "The token needs the admin.analytics:read user scope.",
    "no_permission": "The token's owner must be an Org Owner or Admin.",
    "not_an_admin": "The token's owner must be an Org Owner or Admin.",
    "access_denied": "The token's owner must be an Org Owner or Admin with analytics access.",
    "not_allowed_token_type": "Use the User OAuth Token (xoxp-...), not the bot token.",
    "feature_not_enabled": "Member analytics are only available on Enterprise Grid, with the app installed on the organization.",
    "team_access_not_granted": "Install the app on the whole organization (org-level), not a single workspace.",
    "org_login_required": "Install the app on the whole organization (org-level), not a single workspace.",
    "invalid_auth": "Slack rejected the analytics token - generate a new one.",
    "token_revoked": "Slack rejected the analytics token - generate a new one.",
    "token_expired": "Slack rejected the analytics token - generate a new one.",
    "not_authed": "Slack rejected the analytics token - generate a new one.",
}


def explain(err: str) -> str:
    return EXPLAIN.get(err, f"Slack said: {err}")


def parse_member_file(content: bytes):
    """Return (rows, None) for a member-analytics file, or (None, error_code) for an error response."""
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except (OSError, EOFError):
            return None, "bad_response"
    text = content.decode("utf-8", errors="replace").strip()
    if not text:
        return [], None
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            if not rows:
                return None, "bad_response"
            continue
        if not rows and isinstance(row, dict) and row.get("ok") is False:
            return None, row.get("error") or "unknown_error"
        if isinstance(row, dict):
            rows.append(row)
    return rows, None


def _day(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@register
class SlackConnector(Connector):
    key = "slack"
    name = "Slack"
    vendor = "Slack"
    description = ("Account type for every Slack user (member, admin, owner, guest, deactivated). On Enterprise Grid, add an "
                   "analytics token to also get real last-active dates - Okta can't see Slack use because people stay signed in.")
    color = "#4A154B"
    initials = "Sl"
    provides = ("Account type", "Deactivated accounts", "Last active (Enterprise Grid)")
    app_aliases = ("slack",)
    fields = (
        Field("bot_token", "Bot User OAuth Token", type="password", secret=True,
              help="Starts with xoxb-", placeholder="xoxb-..."),
        Field("analytics_token", "Analytics user token (Enterprise Grid, optional)", type="password", secret=True,
              required=False, help="Starts with xoxp-. A user token from an Org Owner/Admin with the admin.analytics:read scope. "
                                   "Gives real last-active dates.", placeholder="xoxp-..."),
    )
    guide = Guide(
        steps=(
            "Go to api.slack.com/apps and choose Create New App > From scratch.",
            "Under OAuth & Permissions > Bot Token Scopes, add users:read and users:read.email. To let Reclamation message people "
            "(\"do you still need this?\"), also add chat:write.",
            "Click Install to Workspace and copy the Bot User OAuth Token (xoxb-...).",
            "Enterprise Grid, for real last-active dates: in the same app add the User Token Scope admin.analytics:read, enable "
            "org-level deployment for the app, and have an Org Owner or Admin install it on the organization. Copy the User OAuth "
            "Token (xoxp-...) into 'Analytics user token'.",
            "Slack must be allowed to show email addresses for the organization, or member analytics are blocked.",
            "The first sync reads up to 90 daily files and takes several minutes; after that it only reads new days.",
        ),
        docs_url="https://api.slack.com/methods/admin.analytics.getFile",
    )

    async def _call(self, client, method, token, params=None):
        resp = await send(client, "GET", f"{API}/{method}",
                          params=params or {}, headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        if not data.get("ok"):
            raise ConnectorError(f"Slack said: {data.get('error', 'unknown error')}")
        return data

    async def _fetch_day(self, client, token, day):
        """(rows, None) or (None, error_code) for one day of member analytics."""
        try:
            resp = await send(client, "GET", f"{API}/admin.analytics.getFile",
                              params={"type": "member", "date": day.isoformat()},
                              headers={"Authorization": f"Bearer {token}"})
        except ConnectorError as exc:
            return None, f"request_failed: {exc}"[:160]
        return parse_member_file(resp.content)

    async def test(self, cfg, db=None) -> str:
        async with self.make_client() as client:
            data = await self._call(client, "auth.test", cfg["bot_token"])
            message = f"Connected to the {data.get('team', 'Slack')} workspace"
            token = (cfg.get("analytics_token") or "").strip()
            if token:
                today = datetime.now(timezone.utc).date()
                err = None
                for back in (1, 2):
                    rows, err = await self._fetch_day(client, token, today - timedelta(days=back))
                    if err is None:
                        message += f"; activity data readable ({len(rows):,} people on {(today - timedelta(days=back)).isoformat()})"
                        break
                    if err in FATAL:
                        break
                if err is not None:
                    message += f"; activity data NOT readable ({explain(err)})"
        return message

    async def _members(self, client, token) -> list:
        records, cursor = [], None
        while True:
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = await self._call(client, "users.list", token, params)
            for m in data.get("members", []):
                if m.get("is_bot") or m.get("id") == "USLACKBOT":
                    continue
                profile = m.get("profile") or {}
                email = (profile.get("email") or "").strip()
                if not email:
                    continue
                if m.get("deleted"):
                    label = "deactivated"
                elif m.get("is_owner"):
                    label = "owner"
                elif m.get("is_admin"):
                    label = "admin"
                elif m.get("is_ultra_restricted"):
                    label = "single-channel guest"
                elif m.get("is_restricted"):
                    label = "guest"
                else:
                    label = "member"
                records.append(UserRecord(email=email, license_type=label,
                                          full_name=profile.get("real_name") or m.get("real_name")))
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return records

    async def _activity(self, client, token, saved: dict):
        """Update {email: last active day} from the daily files not yet read. Returns (last_active, saved_state)."""
        today = datetime.now(timezone.utc).date()
        newest = today - timedelta(days=1)                   # today's file isn't ready yet
        through = _day(saved.get("through"))
        history_start = _day(saved.get("history_start"))
        last_active = dict(saved.get("last_active") or {})

        start = newest - timedelta(days=HISTORY_DAYS - 1)
        if through is not None:
            start = max(start, through + timedelta(days=1))
        days = [newest - timedelta(days=i) for i in range(max(0, (newest - start).days + 1))]   # newest first

        fetched, misses, last_err = 0, 0, None
        newest_ok, oldest_ok = None, None
        for n, day in enumerate(days):
            if n:
                await asyncio.sleep(CALL_DELAY)
            rows, err = await self._fetch_day(client, token, day)
            if err is not None:
                if err in FATAL:
                    raise ConnectorError(explain(err))
                last_err, misses = err, misses + 1
                if fetched == 0 and misses >= STOP_AFTER_MISSES:
                    raise ConnectorError(f"Could not read Slack activity ({explain(last_err)})")
                if fetched and misses >= STOP_AFTER_MISSES:
                    break                                   # ran out of history
                continue
            misses, fetched = 0, fetched + 1
            newest_ok = newest_ok or day
            oldest_ok = day
            iso = day.isoformat()
            for row in rows:
                email = (row.get("email_address") or "").strip().lower()
                if email and row.get("is_active") and last_active.get(email, "") < iso:
                    last_active[email] = iso

        new_through = max([d for d in (through, newest_ok) if d], default=None)
        new_start = min([d for d in (history_start, oldest_ok) if d], default=None)
        state = {"last_active": last_active,
                 "through": new_through.isoformat() if new_through else None,
                 "history_start": new_start.isoformat() if new_start else None}
        return last_active, state

    async def fetch_users(self, cfg):
        token = (cfg.get("analytics_token") or "").strip()
        async with self.make_client() as client:
            records = await self._members(client, cfg["bot_token"])
            if not token:
                return records
            saved = (self.state_in or {}).get("activity") or {}
            last_active, state = await self._activity(client, token, saved)

        self.state_out = {"activity": state}
        by_email = {r.email.strip().lower(): r for r in records}
        for email, iso in last_active.items():
            when = datetime.strptime(iso, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
            if email in by_email:
                by_email[email].last_active_at = when
            else:
                records.append(UserRecord(email=email, license_type="member", last_active_at=when))

        notes = []
        through, start = _day(state["through"]), _day(state["history_start"])
        if through and start:
            span = (through - start).days + 1
            notes.append(f"Slack activity covers {start.isoformat()} to {through.isoformat()} ({span} days).")
            if span < HISTORY_DAYS - 3:
                notes.append(f"Slack provided only {span} days of history, so use inactivity thresholds of {span} days or less.")
        return records, notes
