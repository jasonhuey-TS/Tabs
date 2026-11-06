"""Salesforce - user license, profile, last login and inactive users via SOQL."""
from urllib.parse import urlparse

from .base import Connector, ConnectorError, Field, Guide, UserRecord, parse_dt, send
from .registry import register

API_VERSION = "v60.0"
SOQL = ("SELECT Email, Name, IsActive, LastLoginDate, Profile.Name, Profile.UserLicense.Name "
        "FROM User WHERE UserType = 'Standard'")


def normalize_domain(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        raise ConnectorError("Enter your Salesforce My Domain URL, e.g. https://yourcompany.my.salesforce.com")
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    return f"https://{parsed.netloc}"


@register
class SalesforceConnector(Connector):
    key = "salesforce"
    name = "Salesforce"
    vendor = "Salesforce"
    description = "Salesforce license type, last login and inactive users, straight from the User object."
    color = "#00A1E0"
    initials = "Sf"
    provides = ("License type", "Last login", "Inactive users")
    app_aliases = ("salesforce",)
    fields = (
        Field("domain", "My Domain URL", placeholder="https://yourcompany.my.salesforce.com",
              help="Use your sandbox's domain to connect a sandbox instead."),
        Field("client_id", "Consumer Key"),
        Field("client_secret", "Consumer Secret", type="password", secret=True),
    )
    guide = Guide(
        steps=(
            "In Salesforce Setup open App Manager and create a New External Client App (or New Connected App on older orgs).",
            "Enable OAuth with the 'Manage user data via APIs (api)' scope and turn on the Client Credentials Flow.",
            "Set a 'Run As' user that has API access and permission to view users.",
            "Copy the Consumer Key and Consumer Secret, and paste them here with your My Domain URL.",
        ),
    )

    async def _login(self, client, cfg):
        domain = normalize_domain(cfg["domain"])
        resp = await send(client, "POST", f"{domain}/services/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"]})
        data = resp.json()
        if not data.get("access_token"):
            raise ConnectorError("Salesforce did not return an access token - check the key, secret and domain.")
        return (data.get("instance_url") or domain).rstrip("/"), data["access_token"]

    async def test(self, cfg, db=None) -> str:
        async with self.make_client() as client:
            instance, token = await self._login(client, cfg)
            resp = await send(client, "GET", f"{instance}/services/data/{API_VERSION}/query",
                              params={"q": "SELECT COUNT() FROM User WHERE IsActive = true AND UserType = 'Standard'"},
                              headers={"Authorization": f"Bearer {token}"})
        total = resp.json().get("totalSize")
        return "Connected to Salesforce" + (f" - {total:,} active users" if isinstance(total, int) else "")

    async def fetch_users(self, cfg) -> list:
        records = []
        async with self.make_client() as client:
            instance, token = await self._login(client, cfg)
            headers = {"Authorization": f"Bearer {token}"}
            url, params = f"{instance}/services/data/{API_VERSION}/query", {"q": SOQL}
            while url:
                data = (await send(client, "GET", url, params=params, headers=headers)).json()
                for u in data.get("records", []):
                    email = (u.get("Email") or "").strip()
                    if not email:
                        continue
                    profile = u.get("Profile") or {}
                    license_name = ((profile.get("UserLicense") or {}).get("Name")) or profile.get("Name") or "unknown"
                    label = license_name if u.get("IsActive") else "inactive"
                    records.append(UserRecord(email=email, license_type=label[:100],
                                              last_active_at=parse_dt(u.get("LastLoginDate")),
                                              full_name=u.get("Name")))
                next_path = data.get("nextRecordsUrl")
                url, params = (f"{instance}{next_path}" if next_path and not data.get("done") else None), None
        return records
