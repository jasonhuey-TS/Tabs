"""Google Workspace - last login, role and suspended accounts via the Admin SDK Directory API."""
import base64
import json
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .base import Connector, ConnectorError, Field, Guide, UserRecord, parse_dt, send
from .registry import register

SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERS_URL = "https://admin.googleapis.com/admin/directory/v1/users"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def build_assertion(sa: dict, admin_email: str, now: int = None, scope: str = SCOPE) -> str:
    """Signed JWT for Google's service-account / domain-wide-delegation flow."""
    now = int(now or time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": sa["client_email"], "sub": admin_email, "scope": scope,
        "aud": sa.get("token_uri") or TOKEN_URI, "iat": now, "exp": now + 3600,
    }
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


@register
class GoogleWorkspaceConnector(Connector):
    key = "google_workspace"
    name = "Google Workspace"
    vendor = "Google"
    description = "Last login, admin role and suspended accounts for every Google Workspace user."
    color = "#EA4335"
    initials = "Gw"
    provides = ("Last login", "Admin role", "Suspended accounts")
    app_aliases = ("google workspace", "g suite", "gsuite", "gmail", "google apps")
    fields = (
        Field("admin_email", "Admin email", placeholder="admin@yourcompany.com",
              help="The work email of a real Workspace super admin (a person, not the service account's own address). The service account acts as this person."),
        Field("service_account_json", "Service account key (JSON)", type="textarea", secret=True,
              help="Paste the full contents of the downloaded JSON key file."),
    )
    guide = Guide(
        steps=(
            "In Google Cloud console, create or pick a project and enable the Admin SDK API.",
            "Create a service account, then add a JSON key and download it.",
            "In admin.google.com go to Security > Access and data control > API controls > Domain-wide delegation > Add new.",
            f"Enter the service account's Client ID and this scope: {SCOPE}",
            "Paste the full JSON key here, and the work email of a Workspace super admin (a person, not the service account's address).",
        ),
        docs_url="https://developers.google.com/admin-sdk/directory/v1/guides/delegation",
    )

    def _sa(self, cfg) -> dict:
        try:
            sa = json.loads(cfg["service_account_json"])
        except (ValueError, TypeError):
            raise ConnectorError("The service account key isn't valid JSON - paste the whole downloaded file.")
        if not isinstance(sa, dict) or not sa.get("client_email") or not sa.get("private_key"):
            raise ConnectorError("That doesn't look like a service account key (client_email / private_key missing).")
        return sa

    @staticmethod
    def _check_admin(cfg, sa) -> str:
        """The 'Admin email' has to be a real person who is a Workspace admin: the service account acts AS that person. Catches the usual slips before asking Google."""
        admin = str(cfg.get("admin_email") or "").strip()
        own = str(sa.get("client_email") or "").strip().lower()
        if "@" not in admin:
            raise ConnectorError("Enter an email address in 'Admin email': the work address of a Google Workspace super admin.")
        if admin.lower() == own or admin.lower().endswith(".gserviceaccount.com"):
            raise ConnectorError(f"'Admin email' is the service account's own address ({admin}). It must be the work email of a real Google Workspace super admin: the service account acts as that person.")
        return admin

    @staticmethod
    def _explain(exc: ConnectorError, admin: str) -> ConnectorError:
        """Google's own wording for these two mistakes says nothing useful, so say what it means."""
        msg = str(exc)
        if "returned 400" in msg and "Invalid Input" in msg:
            return ConnectorError(f"Google accepted the key but would not list users as {admin}. This almost always means {admin} is not a Workspace super admin, or is not a real user in your domain: "
                                  f"the service account acts as that person, so use a super admin's work email. ({msg[:150]})")
        if "returned 403" in msg and ("Not Authorized" in msg or "notAuthorized" in msg):
            return ConnectorError(f"Google would not let {admin} read the user directory. That account needs admin rights that include reading users, so use a super admin. ({msg[:150]})")
        return exc

    async def _token(self, client, cfg) -> str:
        sa = self._sa(cfg)
        self._check_admin(cfg, sa)
        try:
            assertion = build_assertion(sa, cfg["admin_email"])
        except Exception as exc:
            raise ConnectorError(f"Could not sign the request with that private key: {exc}")
        resp = await send(client, "POST", sa.get("token_uri") or TOKEN_URI, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
        token = resp.json().get("access_token")
        if not token:
            raise ConnectorError("Google did not return an access token.")
        return token

    async def test(self, cfg, db=None) -> str:
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            try:
                await send(client, "GET", USERS_URL, params={"customer": "my_customer", "maxResults": 1}, headers={"Authorization": f"Bearer {token}"})
            except ConnectorError as exc:
                raise self._explain(exc, str(cfg.get("admin_email") or "").strip())
        return "Connected - the user directory is readable"

    async def fetch_users(self, cfg) -> list:
        records, page_token = [], None
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            while True:
                params = {"customer": "my_customer", "maxResults": 500}
                if page_token:
                    params["pageToken"] = page_token
                try:
                    data = (await send(client, "GET", USERS_URL, params=params, headers={"Authorization": f"Bearer {token}"})).json()
                except ConnectorError as exc:
                    raise self._explain(exc, str(cfg.get("admin_email") or "").strip())
                for u in data.get("users", []):
                    email = (u.get("primaryEmail") or "").strip()
                    if not email:
                        continue
                    if u.get("suspended"):
                        label = "suspended"
                    elif u.get("archived"):
                        label = "archived"
                    elif u.get("isAdmin") or u.get("isDelegatedAdmin"):
                        label = "admin"
                    else:
                        label = "user"
                    records.append(UserRecord(
                        email=email, license_type=label,
                        last_active_at=parse_dt(u.get("lastLoginTime")),     # 1970 = never
                        full_name=(u.get("name") or {}).get("fullName")))
                page_token = data.get("nextPageToken")
                if not page_token:
                    return records
