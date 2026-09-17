"""
Zoom integration — pulls user list with last login date and license type.

Requires a Zoom Server-to-Server OAuth app with these scopes:
  user:read:admin, user:read:list_users:admin

Docs: https://developers.zoom.us/docs/api/users/
"""
import httpx
import structlog
from datetime import datetime, timezone

log = structlog.get_logger()

ZOOM_API = "https://api.zoom.us/v2"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"


class ZoomClient:
    def __init__(self, account_id: str, client_id: str, client_secret: str):
        self.account_id = account_id.strip()
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=ZOOM_API, timeout=30.0)
        await self._acquire_token()
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _acquire_token(self) -> None:
        """Get OAuth2 access token using Server-to-Server OAuth."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                ZOOM_TOKEN_URL,
                params={"grant_type": "account_credentials", "account_id": self.account_id},
                auth=(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        self._client.headers.update({"Authorization": f"Bearer {self._token}"})

    async def _paginate(self, path: str, params: dict = None) -> list[dict]:
        results = []
        page_token = None
        while True:
            p = dict(params or {})
            p["page_size"] = 300
            if page_token:
                p["next_page_token"] = page_token
            resp = await self._client.get(path, params=p)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("users", []))
            page_token = data.get("next_page_token")
            if not page_token:
                break
        return results

    async def list_users(self, status: str = "active") -> list[dict]:
        """Return users with given status: active, inactive, pending."""
        log.info("zoom.list_users.start", status=status)
        users = await self._paginate("/users", params={"status": status})
        log.info("zoom.list_users.done", count=len(users), status=status)
        return users

    async def list_all_users(self) -> list[dict]:
        """Return active + inactive users."""
        active = await self.list_users("active")
        inactive = await self.list_users("inactive")
        return active + inactive

    async def test_connection(self) -> dict:
        resp = await self._client.get("/users/me")
        resp.raise_for_status()
        return resp.json()


def normalize_zoom_user(user: dict) -> dict:
    """Extract relevant fields from a Zoom user object."""
    # License types: 1=Basic, 2=Licensed, 3=On-Prem, 99=None
    license_map = {1: "basic", 2: "licensed", 3: "on-prem", 99: "none"}
    license_type = license_map.get(user.get("type"), "unknown")

    last_login = None
    if user.get("last_login_time"):
        try:
            last_login = datetime.fromisoformat(
                user["last_login_time"].replace("Z", "+00:00")
            ).isoformat()
        except Exception:
            pass

    return {
        "zoom_user_id": user.get("id"),
        "email": user.get("email", ""),
        "full_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("email", ""),
        "license_type": license_type,
        "status": user.get("status", "active"),
        "last_login_at": last_login,
        "department": user.get("dept", ""),
        "job_title": user.get("job_title", ""),
        "pmi": user.get("pmi"),
    }
