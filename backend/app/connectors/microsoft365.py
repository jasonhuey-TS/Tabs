"""Microsoft 365 - assigned license (SKU), last sign-in and disabled accounts via Microsoft Graph."""
from .base import Connector, ConnectorError, Field, Guide, UserRecord, parse_dt, send
from .registry import register

GRAPH = "https://graph.microsoft.com/v1.0"

# Friendly names for the most common SKUs; anything else falls back to Microsoft's part number.
SKU_NAMES = {
    "SPE_E5": "Microsoft 365 E5", "SPE_E3": "Microsoft 365 E3", "SPE_F1": "Microsoft 365 F3",
    "ENTERPRISEPREMIUM": "Office 365 E5", "ENTERPRISEPACK": "Office 365 E3", "STANDARDPACK": "Office 365 E1",
    "O365_BUSINESS_PREMIUM": "Microsoft 365 Business Standard", "O365_BUSINESS_ESSENTIALS": "Microsoft 365 Business Basic",
    "SPB": "Microsoft 365 Business Premium", "EMS": "Enterprise Mobility + Security E3",
    "EMSPREMIUM": "Enterprise Mobility + Security E5", "POWER_BI_PRO": "Power BI Pro",
    "FLOW_FREE": "Power Automate Free", "TEAMS_EXPLORATORY": "Teams Exploratory",
    "VISIOCLIENT": "Visio Plan 2", "PROJECTPROFESSIONAL": "Project Plan 3",
}


@register
class Microsoft365Connector(Connector):
    key = "microsoft365"
    name = "Microsoft 365"
    vendor = "Microsoft"
    description = "Which Microsoft 365 license each person holds, their last sign-in, and disabled accounts."
    color = "#0078D4"
    initials = "M3"
    provides = ("License (SKU)", "Last sign-in", "Disabled accounts")
    app_aliases = ("microsoft 365", "office 365", "microsoft office", "o365")
    fields = (
        Field("tenant_id", "Tenant ID"),
        Field("client_id", "Application (client) ID"),
        Field("client_secret", "Client secret value", type="password", secret=True),
    )
    guide = Guide(
        steps=(
            "In the Microsoft Entra admin center go to App registrations > New registration.",
            "Under API permissions add Microsoft Graph APPLICATION permissions: User.Read.All, AuditLog.Read.All, Organization.Read.All - then Grant admin consent.",
            "Under Certificates & secrets create a new client secret and copy its Value (not the ID).",
            "Paste the Tenant ID, Application (client) ID and the secret value here.",
            "Sign-in dates need Entra ID P1 or P2. Without it you still get licenses, just no last-sign-in.",
        ),
        docs_url="https://learn.microsoft.com/en-us/graph/auth-v2-service",
    )

    async def _token(self, client, cfg) -> str:
        resp = await send(client, "POST",
                          f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
                          data={"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                "scope": "https://graph.microsoft.com/.default",
                                "grant_type": "client_credentials"})
        token = resp.json().get("access_token")
        if not token:
            raise ConnectorError("Microsoft did not return an access token - check the three credentials.")
        return token

    async def test(self, cfg, db=None) -> str:
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            resp = await send(client, "GET", f"{GRAPH}/users", params={"$top": 1, "$select": "id"},
                              headers={"Authorization": f"Bearer {token}"})
        resp.json()
        return "Connected to Microsoft 365 - the user directory is readable"

    async def _sku_names(self, client, headers) -> dict:
        resp = await send(client, "GET", f"{GRAPH}/subscribedSkus", headers=headers)
        return {s["skuId"]: SKU_NAMES.get(s.get("skuPartNumber"), s.get("skuPartNumber") or "Unknown license")
                for s in resp.json().get("value", []) if s.get("skuId")}

    async def _users(self, client, headers, with_signins: bool) -> list:
        fields = "id,displayName,mail,userPrincipalName,accountEnabled,assignedLicenses"
        if with_signins:
            fields += ",signInActivity"
        url, params, users = f"{GRAPH}/users", {"$select": fields, "$top": 500}, []
        while url:
            data = (await send(client, "GET", url, params=params, headers=headers)).json()
            users.extend(data.get("value", []))
            url, params = data.get("@odata.nextLink"), None      # nextLink already carries the query
        return users

    async def fetch_users(self, cfg) -> list:
        async with self.make_client() as client:
            token = await self._token(client, cfg)
            headers = {"Authorization": f"Bearer {token}"}
            skus = await self._sku_names(client, headers)
            notes = []
            try:
                raw = await self._users(client, headers, with_signins=True)
            except ConnectorError:
                # Tenants without Entra ID P1/P2 reject signInActivity; fall back to licenses only.
                raw = await self._users(client, headers, with_signins=False)
                notes.append("Last sign-in dates unavailable (needs Entra ID P1/P2 and AuditLog.Read.All).")
        records = []
        for u in raw:
            email = (u.get("mail") or u.get("userPrincipalName") or "").strip()
            if not email:
                continue
            names = [skus.get(l.get("skuId"), "Unknown license") for l in u.get("assignedLicenses") or []]
            if u.get("accountEnabled") is False:
                label = "disabled"
            elif not names:
                label = "unlicensed"
            else:
                label = names[0] + (f" +{len(names) - 1}" if len(names) > 1 else "")
            activity = u.get("signInActivity") or {}
            seen = [d for d in (parse_dt(activity.get("lastSignInDateTime")),
                                parse_dt(activity.get("lastNonInteractiveSignInDateTime"))) if d]
            records.append(UserRecord(email=email, license_type=label[:100],
                                      last_active_at=max(seen) if seen else None,
                                      full_name=u.get("displayName")))
        return (records, notes) if notes else records
