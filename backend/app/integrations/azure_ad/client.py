"""
Azure AD / Entra ID integration via Microsoft Graph API.

Docs: https://learn.microsoft.com/en-us/graph/api/serviceprincipal-list
      https://learn.microsoft.com/en-us/graph/api/user-list
"""
import httpx
import structlog
from datetime import datetime
from app.core.config import settings

log = structlog.get_logger()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class AzureADClient:
    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.tenant_id = tenant_id or settings.AZURE_TENANT_ID
        self.client_id = client_id or settings.AZURE_CLIENT_ID
        self.client_secret = client_secret or settings.AZURE_CLIENT_SECRET
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=GRAPH_BASE, timeout=30.0)
        await self._acquire_token()
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _acquire_token(self) -> None:
        token_url = TOKEN_URL.format(tenant_id=self.tenant_id)
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            })
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        self._client.headers.update({"Authorization": f"Bearer {self._token}"})

    async def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        """Follow OData @odata.nextLink pagination."""
        results = []
        url = path
        while url:
            resp = await self._client.get(url, params=params if not url.startswith("https") else None)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            params = None
        return results

    async def list_service_principals(self) -> list[dict]:
        """Return all enterprise app / service principals (= SaaS apps with SSO)."""
        log.info("azure_ad.list_service_principals.start")
        sps = await self._paginate("/servicePrincipals", params={
            "$select": "id,displayName,appId,homepage,publisherName,tags,appRoleAssignmentRequired,signInAudience",
            "$top": 999,
        })
        log.info("azure_ad.list_service_principals.done", count=len(sps))
        return sps

    async def list_app_role_assignments(self, service_principal_id: str) -> list[dict]:
        """Return users/groups assigned to an app."""
        return await self._paginate(
            f"/servicePrincipals/{service_principal_id}/appRoleAssignedTo",
            params={"$top": 999},
        )

    async def list_users(self) -> list[dict]:
        """Return all enabled users."""
        log.info("azure_ad.list_users.start")
        users = await self._paginate("/users", params={
            "$select": "id,displayName,mail,userPrincipalName,department,signInActivity",
            "$filter": "accountEnabled eq true",
            "$top": 999,
        })
        log.info("azure_ad.list_users.done", count=len(users))
        return users


def normalize_azure_app(sp: dict) -> dict:
    """Map Azure AD service principal to our internal app schema."""
    name = sp.get("displayName", "")
    vendor = sp.get("publisherName") or name
    vendor_slug = name.lower().replace(" ", "-")
    return {
        "name": name,
        "vendor": vendor,
        "vendor_slug": vendor_slug,
        "website": sp.get("homepage"),
        "discovered_via": "azure_ad",
        "is_shadow_it": False,
        "status": "managed",
        "meta": {
            "azure_sp_id": sp.get("id"),
            "azure_app_id": sp.get("appId"),
            "tags": sp.get("tags", []),
        },
    }
