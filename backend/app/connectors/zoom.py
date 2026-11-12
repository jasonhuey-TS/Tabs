"""Zoom - Basic vs Licensed accounts, last login, deactivated accounts, account details and (with the Reports permission) meeting totals."""
from datetime import datetime, timedelta, timezone

from .base import AttributeField, Connector, ConnectorError, Field, Guide, UserRecord, parse_dt, send
from .registry import register

# Zoom "type": 1 Basic, 2 Licensed, 4 Unassigned without Meetings Basic (no license).
_LICENSE = {1: "basic", 2: "licensed", 3: "on-prem", 4: "unassigned", 99: "none"}


@register
class ZoomConnector(Connector):
    key = "zoom"
    name = "Zoom"
    vendor = "Zoom"
    description = "Which Zoom accounts hold a paid license, and when each person last logged in."
    color = "#2D8CFF"
    initials = "Zm"
    provides = ("License type", "Last login", "Deactivated accounts", "Account details", "Meeting totals (needs the Reports permission)")
    attribute_fields = (
        AttributeField("created_at", "Created At", "date"),
        AttributeField("status", "Account Status", "enum"),
        AttributeField("dept", "Department (in Zoom)", "enum"),
        AttributeField("last_client_version", "Last Client Version", "enum"),
        AttributeField("verified", "Email Verified", "bool"),
        AttributeField("timezone", "Time Zone", "enum"),
        AttributeField("language", "Language", "enum"),
        AttributeField("meetings_90d", "Meetings Hosted (last 90 days)", "number"),
        AttributeField("participants_90d", "Participants in Hosted Meetings (last 90 days)", "number"),
        AttributeField("minutes_90d", "Meeting Minutes Hosted (last 90 days)", "number"),
        AttributeField("avg_minutes", "Average Meeting Minutes", "number"),
        AttributeField("avg_participants", "Average Participants per Meeting", "number"),
    )
    app_aliases = ("zoom",)
    fields = (
        Field("account_id", "Account ID"),
        Field("client_id", "Client ID"),
        Field("client_secret", "Client Secret", type="password", secret=True),
    )
    guide = Guide(
        steps=(
            "Sign in at marketplace.zoom.us as a Zoom admin and choose Develop > Build App > Server-to-Server OAuth > Create.",
            "On App Credentials, copy the Account ID, Client ID and Client Secret.",
            "On Information, add a short description, company name and a developer contact (Zoom requires these to activate).",
            "On Scopes, add 'View all user information' (user:read:admin), or user:read:list_users:admin.",
            "Optional: also add 'View all user reports' (report:read:admin) to collect each person's meeting totals. Zoom's Reports need a Pro or higher plan; without this, everything else still works.",
            "On Activation, click Activate your app, then paste the three values here.",
        ),
        docs_url="https://developers.zoom.us/docs/internal-apps/create/",
    )

    async def _token(self, client, cfg) -> str:
        resp = await send(
            client, "POST", "https://zoom.us/oauth/token",
            params={"grant_type": "account_credentials", "account_id": cfg["account_id"]},
            auth=(cfg["client_id"], cfg["client_secret"]),
        )
        token = resp.json().get("access_token")
        if not token:
            raise ConnectorError("Zoom did not return an access token - check the three credentials.")
        return token

    async def _list(self, client, token, status):
        users, page_token = [], None
        while True:
            params = {"status": status, "page_size": 300}
            if page_token:
                params["next_page_token"] = page_token
            resp = await send(client, "GET", "https://api.zoom.us/v2/users",
                              params=params, headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
            users.extend(data.get("users", []))
            page_token = data.get("next_page_token")
            if not page_token:
                return users

    async def _usage(self, client, token, notes):
        """email -> [meetings, participants, minutes] hosted over the last 90 days, from Zoom's Active Hosts report (three 30-day windows,
        as the report covers at most a month). None, with a note, if Zoom refuses (missing permission or plan)."""
        today = datetime.now(timezone.utc).date()
        totals = {}
        try:
            for i in range(3):
                to = today - timedelta(days=30 * i)
                frm = to - timedelta(days=29)
                page_token = None
                while True:
                    params = {"type": "active", "from": frm.isoformat(), "to": to.isoformat(), "page_size": 300}
                    if page_token:
                        params["next_page_token"] = page_token
                    data = (await send(client, "GET", "https://api.zoom.us/v2/report/users", params=params, headers={"Authorization": f"Bearer {token}"})).json()
                    for r in data.get("users") or []:
                        email = (r.get("email") or "").strip().lower()
                        if email:
                            t = totals.setdefault(email, [0, 0, 0])
                            t[0] += int(r.get("meetings") or 0)
                            t[1] += int(r.get("participants") or 0)
                            t[2] += int(r.get("meeting_minutes") or 0)
                    page_token = data.get("next_page_token")
                    if not page_token:
                        break
        except ConnectorError:
            notes.append("Meeting totals weren't collected because Zoom refused the Reports request. Add the 'View all user reports' (report:read:admin) scope to the Zoom app "
                         "(Zoom's Reports need a Pro or higher plan), then sync again.")
            return None
        return totals

    async def test(self, cfg, db=None) -> str:
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            resp = await send(client, "GET", "https://api.zoom.us/v2/users",
                              params={"status": "active", "page_size": 1},
                              headers={"Authorization": f"Bearer {token}"})
        total = resp.json().get("total_records")
        return "Connected to Zoom" + (f" - {total:,} active users visible" if isinstance(total, int) else "")

    async def fetch_users(self, cfg) -> list:
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            raw = await self._list(client, token, "active") + await self._list(client, token, "inactive")
            notes = []
            usage = await self._usage(client, token, notes)
        records = []
        for u in raw:
            email = (u.get("email") or "").strip()
            if not email:
                continue
            label = _LICENSE.get(u.get("type"), "unknown")
            if u.get("status") == "inactive":
                label = "inactive"               # a deactivated account holds no license seat
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("display_name")
            attrs = {"created_at": (u.get("created_at") or u.get("user_created_at")), "status": u.get("status"), "dept": (u.get("dept") or "").strip() or None,
                     "last_client_version": (u.get("last_client_version") or "").strip() or None, "timezone": (u.get("timezone") or "").strip() or None,
                     "language": (u.get("language") or "").strip() or None}
            if u.get("verified") is not None:
                attrs["verified"] = bool(u.get("verified"))
            if usage is not None:                     # the report only lists hosts who hosted something, so everyone else hosted nothing
                meetings, participants, minutes = usage.get(email.lower(), [0, 0, 0])
                attrs.update(meetings_90d=meetings, participants_90d=participants, minutes_90d=minutes)
                if meetings:
                    attrs.update(avg_minutes=round(minutes / meetings, 1), avg_participants=round(participants / meetings, 1))
            records.append(UserRecord(email=email, license_type=label, last_active_at=parse_dt(u.get("last_login_time")), full_name=name,
                                      attributes={k: v for k, v in attrs.items() if v is not None}))
        return (records, notes) if notes else records
