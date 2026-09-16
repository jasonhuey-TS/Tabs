"""
Okta integration — pulls all OAuth app grants and active users via the Okta Management API.

Docs: https://developer.okta.com/docs/reference/api/apps/
      https://developer.okta.com/docs/reference/api/users/
"""
import httpx
import structlog
from datetime import datetime, timezone
from app.core.config import settings

log = structlog.get_logger()

OKTA_API_BASE = "https://{domain}/api/v1"


class OktaClient:
    def __init__(self, domain: str | None = None, api_token: str | None = None):
        self.domain = domain or settings.OKTA_DOMAIN
        self.api_token = api_token or settings.OKTA_API_TOKEN
        self.base_url = OKTA_API_BASE.format(domain=self.domain)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"SSWS {self.api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        """Follow Okta's Link header pagination and collect all results."""
        results = []
        url = path
        while url:
            resp = await self._client.get(url, params=params if url == path else None)
            resp.raise_for_status()
            results.extend(resp.json())
            # Okta uses Link header for next page
            link = resp.headers.get("link", "")
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    # Strip base_url prefix so relative path works
                    if next_url.startswith(self.base_url):
                        next_url = next_url[len(self.base_url):]
                    break
            url = next_url
            params = None  # params only on first request
        return results

    async def list_apps(self) -> list[dict]:
        """Return all apps (including OAuth/OIDC and SAML) configured in Okta."""
        log.info("okta.list_apps.start")
        apps = await self._paginate("/apps", params={"limit": 200})
        log.info("okta.list_apps.done", count=len(apps))
        return apps

    async def list_app_users(self, app_id: str) -> list[dict]:
        """Return all users assigned to a specific Okta app."""
        return await self._paginate(f"/apps/{app_id}/users", params={"limit": 500})

    async def list_users(self) -> list[dict]:
        """Return all active users in the org."""
        log.info("okta.list_users.start")
        users = await self._paginate("/users", params={"filter": 'status eq "ACTIVE"', "limit": 200})
        log.info("okta.list_users.done", count=len(users))
        return users

    async def get_user_last_login(self, user_id: str) -> datetime | None:
        resp = await self._client.get(f"/users/{user_id}")
        resp.raise_for_status()
        data = resp.json()
        last_login = data.get("lastLogin")
        if last_login:
            return datetime.fromisoformat(last_login.replace("Z", "+00:00"))
        return None


def normalize_okta_app(okta_app: dict) -> dict:
    """Map Okta app dict to our internal app schema fields."""
    label = okta_app.get("label", "")
    vendor_slug = label.lower().replace(" ", "-").replace("_", "-")
    return {
        "name": label,
        "vendor": label,
        "vendor_slug": vendor_slug,
        "discovered_via": "okta",
        "is_shadow_it": False,  # Okta-managed apps are not shadow IT
        "status": "managed",
        "meta": {
            "okta_app_id": okta_app.get("id"),
            "okta_sign_on_mode": okta_app.get("signOnMode"),
            "okta_status": okta_app.get("status"),
        },
    }
