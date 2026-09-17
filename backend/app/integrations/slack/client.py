"""
Slack integration — pulls user list with last active date and license type.

Requires a Slack Bot token with these scopes:
  users:read, users:read.email, users.profile:read, admin.users:read (for last active)

Docs: https://api.slack.com/methods/users.list
      https://api.slack.com/methods/users.getPresence
"""
import httpx
import structlog
from datetime import datetime, timezone

log = structlog.get_logger()

SLACK_API = "https://slack.com/api"


class SlackClient:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token.strip()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=SLACK_API,
            headers={"Authorization": f"Bearer {self.bot_token}"},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _get(self, method: str, params: dict = None) -> dict:
        resp = await self._client.get(f"/{method}", params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Slack API error: {data.get('error', 'unknown')}")
        return data

    async def test_auth(self) -> dict:
        """Verify token is valid."""
        return await self._get("auth.test")

    async def list_users(self) -> list[dict]:
        """Return all non-bot, non-deleted workspace members."""
        users = []
        cursor = None
        while True:
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = await self._get("users.list", params)
            members = data.get("members", [])
            # Filter out bots and deleted users
            users.extend([
                m for m in members
                if not m.get("is_bot") and not m.get("deleted") and m.get("id") != "USLACKBOT"
            ])
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        log.info("slack.list_users.done", count=len(users))
        return users

    async def get_user_presence(self, user_id: str) -> str | None:
        """Get presence status — active/away."""
        try:
            data = await self._get("users.getPresence", {"user": user_id})
            return data.get("presence")
        except Exception:
            return None


def normalize_slack_user(member: dict) -> dict:
    """Extract relevant fields from a Slack user object."""
    profile = member.get("profile", {})

    # Determine license type
    if member.get("is_admin") or member.get("is_owner"):
        license_type = "admin"
    elif member.get("is_restricted"):
        license_type = "guest"
    elif member.get("is_ultra_restricted"):
        license_type = "single-channel-guest"
    else:
        license_type = "full"

    # Last active — Slack provides this via updated field or profile.status_expiration
    # The most reliable is profile.last_updated for Enterprise Grid
    last_active = None
    if profile.get("last_updated"):
        try:
            last_active = datetime.fromtimestamp(profile["last_updated"], tz=timezone.utc).isoformat()
        except Exception:
            pass

    return {
        "slack_user_id": member.get("id"),
        "email": profile.get("email", ""),
        "full_name": profile.get("real_name") or member.get("real_name") or profile.get("email", ""),
        "display_name": profile.get("display_name") or profile.get("real_name", ""),
        "license_type": license_type,
        "is_admin": member.get("is_admin", False),
        "last_active_at": last_active,
        "title": profile.get("title", ""),
        "timezone": member.get("tz", ""),
    }
