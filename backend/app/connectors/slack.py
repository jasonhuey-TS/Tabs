"""Slack - member / admin / owner / guest accounts and deactivated accounts."""
from .base import Connector, ConnectorError, Field, Guide, UserRecord, send
from .registry import register


@register
class SlackConnector(Connector):
    key = "slack"
    name = "Slack"
    vendor = "Slack"
    description = ("Account type for every Slack user: member, admin, owner or guest, and who is deactivated. "
                   "Slack's API doesn't expose last-active dates; sign-in activity comes from Okta.")
    color = "#4A154B"
    initials = "Sl"
    provides = ("Account type", "Deactivated accounts")
    app_aliases = ("slack",)
    fields = (
        Field("bot_token", "Bot User OAuth Token", type="password", secret=True,
              help="Starts with xoxb-", placeholder="xoxb-..."),
    )
    guide = Guide(
        steps=(
            "Go to api.slack.com/apps and choose Create New App > From scratch.",
            "Under OAuth & Permissions > Bot Token Scopes, add users:read and users:read.email. To let Reclamation message people (\"do you still need this?\"), also add chat:write.",
            "Click Install to Workspace and copy the Bot User OAuth Token (xoxb-...).",
        ),
        docs_url="https://api.slack.com/apps",
    )

    async def _call(self, client, method, token, params=None):
        resp = await send(client, "GET", f"https://slack.com/api/{method}",
                          params=params or {}, headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        if not data.get("ok"):
            raise ConnectorError(f"Slack said: {data.get('error', 'unknown error')}")
        return data

    async def test(self, cfg, db=None) -> str:
        async with self.make_client() as client:
            data = await self._call(client, "auth.test", cfg["bot_token"])
        return f"Connected to the {data.get('team', 'Slack')} workspace"

    async def fetch_users(self, cfg) -> list:
        records, cursor = [], None
        async with self.make_client() as client:
            while True:
                params = {"limit": 200}
                if cursor:
                    params["cursor"] = cursor
                data = await self._call(client, "users.list", cfg["bot_token"], params)
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
