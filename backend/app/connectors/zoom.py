"""Zoom - Basic vs Licensed accounts, last login, deactivated accounts."""
from .base import Connector, ConnectorError, Field, Guide, UserRecord, parse_dt, send
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
    provides = ("License type", "Last login", "Deactivated accounts")
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
        records = []
        for u in raw:
            email = (u.get("email") or "").strip()
            if not email:
                continue
            label = _LICENSE.get(u.get("type"), "unknown")
            if u.get("status") == "inactive":
                label = "inactive"               # a deactivated account holds no license seat
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("display_name")
            records.append(UserRecord(email=email, license_type=label,
                                      last_active_at=parse_dt(u.get("last_login_time")), full_name=name))
        return records
