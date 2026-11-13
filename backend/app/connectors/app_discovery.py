"""
App discovery - finds apps people connected to their Google or Microsoft work account that IT may not know about (shadow IT).

It reuses the credentials saved for the Google Workspace and Microsoft 365 connectors, so there is nothing new to paste; each needs one
extra read-only permission (see the guide below). Either source works on its own, and a missing permission only leaves that source out.
Read-only: it never revokes access or changes anything in Google or Microsoft.
"""
import asyncio
import json
from urllib.parse import quote

from . import discovery_map as dm
from .base import ConnectorError, GlobalConnector, Guide, send
from .google_workspace import TOKEN_URI, build_assertion
from .registry import register

GOOGLE_USERS_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"
GOOGLE_SECURITY_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.security"
DIRECTORY = "https://admin.googleapis.com/admin/directory/v1"
GRAPH = "https://graph.microsoft.com/v1.0"
CONCURRENCY = 8                      # people asked about at once; Google throttles harder than that
MAX_PAGES = 300


async def load_cfgs(db) -> dict:
    """The saved Google Workspace and Microsoft 365 settings, by connector key (a missing or unreadable one is left out)."""
    from sqlalchemy import select
    from app.core.encryption import decrypt
    from app.models.connector_config import ConnectorConfig
    rows = (await db.execute(select(ConnectorConfig).where(ConnectorConfig.key.in_(["google_workspace", "microsoft365"])))).scalars().all()
    out = {}
    for r in rows:
        try:
            out[r.key] = json.loads(decrypt(r.config_encrypted))
        except Exception:
            continue
    return out


def google_ready(cfg) -> bool:
    return bool(cfg and cfg.get("admin_email") and cfg.get("service_account_json"))


def microsoft_ready(cfg) -> bool:
    return bool(cfg and cfg.get("tenant_id") and cfg.get("client_id") and cfg.get("client_secret"))


async def graph_all(client, headers, url, params=None) -> list:
    out, n = [], 0
    while url and n < MAX_PAGES:
        data = (await send(client, "GET", url, params=params, headers=headers)).json()
        out.extend(data.get("value") or [])
        url, params, n = data.get("@odata.nextLink"), None, n + 1
    return out


@register
class AppDiscoveryConnector(GlobalConnector):
    key = "app_discovery"
    name = "App discovery"
    vendor = "Tab"
    description = ("Finds apps people connected to their Google or Microsoft work account that IT may not know about (shadow IT), and how much access each was given. "
                   "Reuses the Google Workspace and Microsoft 365 credentials. Read-only.")
    color = "#7C3AED"
    initials = "Ad"
    provides = ("Apps connected to work accounts", "Who connected them", "How much access they were given")
    fields = ()
    not_ready_message = "Set up Google Workspace or Microsoft 365 in the Integration Library first: app discovery reuses their saved credentials."
    guide = Guide(
        steps=(
            "Google: in admin.google.com open Security > Access and data control > API controls > Domain-wide delegation, edit your service account's entry, and add this scope: "
            f"{GOOGLE_SECURITY_SCOPE}",
            "Microsoft: in the Microsoft Entra admin center open your app registration > API permissions, add the Microsoft Graph APPLICATION permission Directory.Read.All, then Grant admin consent.",
            "Nothing new to paste: discovery reuses the credentials saved on the Google Workspace and Microsoft 365 connectors. Either one is enough.",
        ),
        docs_url="https://developers.google.com/admin-sdk/directory/reference/rest/v1/tokens/list",
    )

    async def is_ready(self, db) -> bool:
        cfgs = await load_cfgs(db)
        return google_ready(cfgs.get("google_workspace")) or microsoft_ready(cfgs.get("microsoft365"))

    # ------------------------------------------------------------------ Google
    async def _google_token(self, client, cfg) -> str:
        try:
            sa = json.loads(cfg["service_account_json"])
            assertion = build_assertion(sa, cfg["admin_email"], scope=f"{GOOGLE_USERS_SCOPE} {GOOGLE_SECURITY_SCOPE}")
        except Exception as exc:
            raise ConnectorError(f"Could not sign the Google request with the saved service account key: {exc}")
        resp = await send(client, "POST", sa.get("token_uri") or TOKEN_URI, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
        token = resp.json().get("access_token")
        if not token:
            raise ConnectorError("Google did not return an access token.")
        return token

    async def _google(self, client, cfg):
        """(records, people asked, people that failed). Raises if Google refused every request: that means the permission is missing."""
        headers = {"Authorization": f"Bearer {await self._google_token(client, cfg)}"}
        emails, page = [], None
        for _ in range(MAX_PAGES):
            params = {"customer": "my_customer", "maxResults": 500, "fields": "users(primaryEmail,suspended,archived),nextPageToken"}
            if page:
                params["pageToken"] = page
            data = (await send(client, "GET", f"{DIRECTORY}/users", params=params, headers=headers)).json()
            emails += [u["primaryEmail"] for u in data.get("users") or [] if u.get("primaryEmail") and not u.get("suspended") and not u.get("archived")]
            page = data.get("nextPageToken")
            if not page:
                break
        per_user, failures, sem = {}, [], asyncio.Semaphore(CONCURRENCY)

        async def one(email):
            async with sem:
                try:
                    per_user[email] = (await send(client, "GET", f"{DIRECTORY}/users/{quote(email, safe='@')}/tokens", headers=headers)).json().get("items") or []
                except ConnectorError as exc:
                    failures.append(exc)

        await asyncio.gather(*(one(e) for e in emails))
        if emails and len(failures) == len(emails):
            raise failures[0]
        return dm.google_records(per_user), len(emails), len(failures)

    # --------------------------------------------------------------- Microsoft
    async def _microsoft_token(self, client, cfg) -> str:
        resp = await send(client, "POST", f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
                          data={"client_id": cfg["client_id"], "client_secret": cfg["client_secret"], "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"})
        token = resp.json().get("access_token")
        if not token:
            raise ConnectorError("Microsoft did not return an access token - check the saved credentials.")
        return token

    async def _microsoft(self, client, cfg):
        headers = {"Authorization": f"Bearer {await self._microsoft_token(client, cfg)}"}
        sps = await graph_all(client, headers, f"{GRAPH}/servicePrincipals",
                              {"$select": "id,appId,displayName,publisherName,appOwnerOrganizationId,servicePrincipalType,createdDateTime,verifiedPublisher,homepage", "$top": 999})
        grants = await graph_all(client, headers, f"{GRAPH}/oauth2PermissionGrants")
        users = await graph_all(client, headers, f"{GRAPH}/users", {"$select": "id,mail,userPrincipalName", "$top": 999})
        return dm.microsoft_records(sps, grants, users, cfg.get("tenant_id")), len(users)

    # --------------------------------------------------------------- test and run
    async def test(self, cfg, db=None) -> str:
        cfgs = await load_cfgs(db) if db is not None else {}
        g, m = cfgs.get("google_workspace"), cfgs.get("microsoft365")
        if not (google_ready(g) or microsoft_ready(m)):
            raise ConnectorError(self.not_ready_message)
        parts = []
        async with self.make_client() as client:
            if google_ready(g):
                try:
                    headers = {"Authorization": f"Bearer {await self._google_token(client, g)}"}
                    await send(client, "GET", f"{DIRECTORY}/users/{quote(g['admin_email'], safe='@')}/tokens", headers=headers)
                    parts.append("Google: can read which apps people authorized.")
                except ConnectorError as exc:
                    parts.append(f"Google: not yet ({str(exc)[:160]}). Add {GOOGLE_SECURITY_SCOPE} to the service account's domain-wide delegation.")
            if microsoft_ready(m):
                try:
                    headers = {"Authorization": f"Bearer {await self._microsoft_token(client, m)}"}
                    await send(client, "GET", f"{GRAPH}/servicePrincipals", params={"$top": 1, "$select": "id"}, headers=headers)
                    await send(client, "GET", f"{GRAPH}/oauth2PermissionGrants", params={"$top": 1}, headers=headers)
                    parts.append("Microsoft: can read enterprise apps and who consented.")
                except ConnectorError as exc:
                    parts.append(f"Microsoft: not yet ({str(exc)[:160]}). Add the Directory.Read.All application permission and grant admin consent.")
        return " ".join(parts)

    async def run(self, db, state, progress):
        from datetime import datetime, timezone
        from . import discovery_apply
        cfgs = await load_cfgs(db)
        g, m = cfgs.get("google_workspace"), cfgs.get("microsoft365")
        if not (google_ready(g) or microsoft_ready(m)):
            raise ConnectorError(self.not_ready_message)
        run_at, notes, sources = datetime.now(timezone.utc), [], {}
        async with self.make_client() as client:
            if google_ready(g):
                await progress("Asking Google which apps people authorized...")
                try:
                    records, asked, failed = await self._google(client, g)
                    sources["google"] = {"people": asked, **await discovery_apply.apply_source(db, "google", records, run_at)}
                    if failed:
                        notes.append(f"Google: {failed:,} of {asked:,} people couldn't be checked (suspended or deleted accounts, or throttling). The rest are included.")
                except ConnectorError as exc:
                    notes.append(f"Google wasn't checked: {str(exc)[:200]}. Add {GOOGLE_SECURITY_SCOPE} to the service account's domain-wide delegation, then sync again.")
            else:
                notes.append("Google wasn't checked: set up the Google Workspace connector to include it.")
            if microsoft_ready(m):
                await progress("Asking Microsoft which apps people consented to...")
                try:
                    records, asked = await self._microsoft(client, m)
                    sources["microsoft"] = {"people": asked, **await discovery_apply.apply_source(db, "microsoft", records, run_at)}
                except ConnectorError as exc:
                    notes.append(f"Microsoft wasn't checked: {str(exc)[:200]}. Add the Directory.Read.All application permission and grant admin consent, then sync again.")
            else:
                notes.append("Microsoft wasn't checked: set up the Microsoft 365 connector to include it.")
        if not sources:
            raise ConnectorError(" ".join(notes))
        found = sum(s["found"] for s in sources.values())
        new = sum(s["found_new"] for s in sources.values())
        named = " and ".join(k.capitalize() for k in sources)
        message = f"Checked {named}: {found:,} apps people connected, {new:,} new to review." + (f" Note: {' '.join(notes)}" if notes else "")
        return {"sources": sources, "found": found, "found_new": new, "notes": notes, "message": message}, {"last_run": run_at.date().isoformat()}
