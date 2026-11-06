"""
Claude (Anthropic) - organization role for every member, plus last activity.

Two different Anthropic keys are involved, because Anthropic issues them separately:

  * Admin API key        -> members and roles          GET /v1/organizations/users
                            seat tier (see below)      GET /v1/organizations/spend_limits/effective
  * Analytics API key    -> last activity per person   GET /v1/organizations/analytics/users
                            (Claude Enterprise only, optional)

Seat tier: Anthropic has no "seat tier" field on members. The Spend Limits API reports, for
each member, WHERE their spend limit comes from; when it is inherited from their seat tier it
names the tier (e.g. "enterprise_standard"). So a tier is only visible for members who inherit
their limit from it - not for members with an individual override, a group limit, or only an
organization-wide default. We say so in a note instead of guessing. When no tier is visible at
all we fall back to the member's role as the label.
"""
from datetime import date, datetime, timedelta, timezone

from .base import Connector, ConnectorError, Field, Guide, UserRecord, parse_dt, send
from .registry import register

API = "https://api.anthropic.com"
VERSION = "2026-10-21"                  # anthropic-version header used by the current Admin API docs
LOOKBACK_DAYS = 90                      # how far back to look for activity
EARLIEST = date(2026, 1, 1)             # Anthropic's analytics data starts here


def _headers(key: str) -> dict:
    return {"x-api-key": key, "anthropic-version": VERSION}


def _tier_label(raw: str) -> str:
    """'enterprise_standard' -> 'standard'; unknown shapes are kept readable."""
    label = (raw or "").strip().lower()
    if label.startswith("enterprise_"):
        label = label[len("enterprise_"):]
    return label.replace("_", " ") or "unknown"


def _window_start(days: int = LOOKBACK_DAYS) -> str:
    return max(EARLIEST, datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


@register
class ClaudeConnector(Connector):
    key = "claude"
    name = "Claude"
    vendor = "Anthropic"
    description = ("Each person's Claude seat tier and role, plus when they were last active. "
                   "Surfaces members who aren't assigned in Okta.")
    color = "#D97757"
    initials = "Cl"
    provides = ("Seat tier", "Member role", "Last activity", "Members not in Okta")
    app_aliases = ("claude", "anthropic")
    fields = (
        Field("admin_api_key", "Admin API key", type="password", secret=True,
              help="Claude Enterprise: a key with the read:members and read:spend_limits scopes (seat tiers). "
                   "Claude Console: an Admin key (sk-ant-admin...) - members and roles only."),
        Field("analytics_api_key", "Analytics API key (optional)", type="password", secret=True, required=False,
              help="Claude Enterprise only. Adds last-activity dates. Needs the read:analytics scope."),
    )
    guide = Guide(
        steps=(
            "Claude Enterprise: the organization's primary owner opens claude.ai > Organization settings > API and enables API access.",
            "Create an Admin API key with the read:members and read:spend_limits scopes and paste it as 'Admin API key'. Usage credits must be turned on for seat tiers to be reported.",
            "Optional, for last-activity dates: create an Analytics API key (read:analytics scope) on the same page and paste it too.",
            "Claude Console (platform): an organization admin creates an Admin key at platform.claude.com/settings/admin-keys. That gives members and roles, but no per-person activity.",
            "Seat tier is reported only for members whose spend limit is inherited from their seat tier. Members with an individual override, a group limit or just an organization-wide default show 'tier not shown'. Setting a spend limit per seat tier in claude.ai makes the tier visible for everyone who has no override.",
        ),
        docs_url="https://platform.claude.com/docs/en/manage-claude/user-management",
    )

    async def _members(self, client, cfg) -> list:
        members, after = [], None
        while True:
            params = {"limit": 1000}
            if after:
                params["after_id"] = after
            data = (await send(client, "GET", f"{API}/v1/organizations/users", params=params,
                               headers=_headers(cfg["admin_api_key"]))).json()
            members.extend(data.get("data", []))
            last_id = data.get("last_id")
            if not data.get("has_more") or not last_id or last_id == after:
                return members
            after = last_id

    async def _seat_tiers(self, client, cfg) -> dict:
        """email -> seat tier, for members whose spend limit is inherited from their seat tier."""
        tiers, page = {}, None
        while True:
            params = {"limit": 100}
            if page:
                params["page"] = page
            data = (await send(client, "GET", f"{API}/v1/organizations/spend_limits/effective", params=params,
                               headers=_headers(cfg["admin_api_key"]))).json()
            for row in data.get("data", []):
                source = row.get("source") or {}
                email = ((row.get("actor") or {}).get("email_address") or "").strip().lower()
                if email and source.get("type") == "seat_tier" and source.get("seat_tier"):
                    tiers[email] = _tier_label(source["seat_tier"])
            page = data.get("next_page")
            if not page:
                return tiers

    async def _activity(self, client, cfg):
        """Returns (email -> last activity datetime, whether Anthropic reported activity dates)."""
        latest, reported, page = {}, False, None
        while True:
            params = {"starting_date": _window_start(), "limit": 1000}
            if page:
                params["page"] = page
            data = (await send(client, "GET", f"{API}/v1/organizations/analytics/users", params=params,
                               headers=_headers(cfg["analytics_api_key"]))).json()
            for row in data.get("data", []):
                if "last_activity_date" in row:          # omitted entirely when the org lacks the feature
                    reported = True
                email = ((row.get("user") or {}).get("email_address") or "").strip().lower()
                when = parse_dt(row.get("last_activity_date"))
                if email and when:
                    latest[email] = when
            page = data.get("next_page")
            if not page:
                return latest, reported

    async def test(self, cfg, db=None) -> str:
        message = "Connected to Claude - the member list is readable"
        async with self.make_client() as client:
            await send(client, "GET", f"{API}/v1/organizations/users", params={"limit": 1},
                       headers=_headers(cfg["admin_api_key"]))
            try:
                await send(client, "GET", f"{API}/v1/organizations/spend_limits/effective", params={"limit": 1},
                           headers=_headers(cfg["admin_api_key"]))
                message += "; seat tiers readable"
            except ConnectorError:
                message += ("; seat tiers NOT readable (the key needs the read:spend_limits scope, "
                            "and usage credits must be on)")
            analytics_key = (cfg.get("analytics_api_key") or "").strip()
            if analytics_key:
                try:
                    data = (await send(client, "GET", f"{API}/v1/organizations/analytics/users",
                                       params={"starting_date": _window_start(7), "limit": 1},
                                       headers=_headers(analytics_key))).json()
                except ConnectorError as exc:
                    raise ConnectorError(f"Members are readable, but the Analytics API key failed: {exc}")
                rows = data.get("data", [])
                if rows and "last_activity_date" not in rows[0]:
                    message += "; the Analytics key works, but Anthropic hasn't enabled last-activity dates for your organization yet"
                else:
                    message += "; the Analytics key works"
        return message

    async def fetch_users(self, cfg):
        notes, activity, tiers = [], {}, {}
        tier_error = None
        async with self.make_client() as client:
            members = await self._members(client, cfg)
            try:
                tiers = await self._seat_tiers(client, cfg)
            except ConnectorError as exc:
                tier_error = str(exc)[:110]
            analytics_key = (cfg.get("analytics_api_key") or "").strip()
            if analytics_key:
                try:
                    activity, reported = await self._activity(client, {**cfg, "analytics_api_key": analytics_key})
                    if not reported:
                        notes.append("Anthropic isn't reporting last-activity dates for this organization yet.")
                except ConnectorError as exc:
                    notes.append(f"Couldn't read activity: {exc}"[:160])

        emails = [(m.get("email") or "").strip().lower() for m in members if (m.get("email") or "").strip()]
        known = sum(1 for e in emails if e in tiers)
        use_tiers = known > 0
        if tier_error:
            notes.insert(0, f"Seat tiers unavailable ({tier_error}); showing roles instead.")
        elif not use_tiers:
            notes.insert(0, "Anthropic reports no seat tier for any member (their spend limits come from overrides, "
                            "groups or the organization default); showing roles instead.")
        elif known < len(emails):
            notes.insert(0, f"Seat tier is visible for {known} of {len(emails)} members; the rest get their spend limit "
                            "from an override, group or the organization default.")

        records = []
        for m in members:
            email = (m.get("email") or "").strip()
            if not email:
                continue
            if use_tiers:
                label = tiers.get(email.lower(), "tier not shown")
            else:
                label = m.get("role") or "member"
            records.append(UserRecord(email=email, license_type=label,
                                      last_active_at=activity.get(email.lower()), full_name=m.get("name")))
        return (records, notes) if notes else records
