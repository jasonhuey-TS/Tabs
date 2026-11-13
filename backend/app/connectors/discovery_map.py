"""Turning what Google and Microsoft report about connected apps into one common shape. Pure functions: no database, no network.

Both answer the same question, "which apps have people connected to their work account, and with what access?":
  Google:    for each person, the third-party apps they authorized (Directory API, tokens.list)
  Microsoft: the enterprise apps, and the delegated-permission grants people (or an admin) consented to (Graph)
"""
from .zylo_map import clean

# The tenants Microsoft's own first-party apps belong to: these are Office, Teams, Azure and so on, never shadow IT.
MICROSOFT_OWNER_TENANTS = {"f8cdef31-a31e-4b4a-93e4-5f571e91255a", "72f988bf-86f1-41af-91ab-2d7cd011db47"}
RANK = {"low": 0, "medium": 1, "high": 2}

_GOOGLE_LABELS = (
    ("mail.google.com", "Full access to Gmail"), ("gmail.modify", "Read, write and delete email"), ("gmail.send", "Send email as the person"), ("gmail.compose", "Write and send email"),
    ("gmail.settings", "Change Gmail settings"), ("gmail.readonly", "Read all email"), ("gmail.metadata", "See email subjects and senders"),
    ("admin.directory", "Read or manage the company directory"), ("cloud-platform", "Use Google Cloud"), ("drive.readonly", "See all files in Drive"), ("drive.metadata", "See Drive file names"),
    ("drive.file", "Only files it creates or the person opens with it"), ("calendar.readonly", "See calendars"), ("calendar", "Manage calendars"), ("contacts.readonly", "See contacts"),
    ("contacts", "Manage contacts"), ("spreadsheets", "Read and edit Google Sheets"), ("documents", "Read and edit Google Docs"), ("presentations", "Read and edit Google Slides"),
    ("forms", "Read and edit Google Forms"), ("youtube", "Use YouTube"), ("photos", "Google Photos"),
)
_MICROSOFT_LABELS = (
    ("mail.readwrite", "Read and write mail"), ("mail.send", "Send mail as the person"), ("mail.read", "Read mail"), ("files.readwrite", "Read and write all files"), ("files.read", "Read all files"),
    ("sites.fullcontrol", "Full control of SharePoint sites"), ("sites.readwrite", "Edit SharePoint sites"), ("sites.read", "Read SharePoint sites"), ("calendars.readwrite", "Manage calendars"),
    ("calendars.read", "See calendars"), ("contacts", "Contacts"), ("chat.readwrite", "Read and write Teams chats"), ("chat.read", "Read Teams chats"), ("directory.readwrite", "Change the company directory"),
    ("directory.read", "Read the company directory"), ("user.readwrite", "Change user profiles"), ("user.read.all", "Read every user's profile"), ("group.readwrite", "Manage groups"),
    ("group.read", "Read groups"), ("user.read", "Sign in and read the person's profile"),
)


def scope_risk(scope: str, source: str) -> str:
    s = str(scope or "").strip().lower()
    if not s:
        return "low"
    if source == "google":
        if s in ("openid", "email", "profile") or "userinfo." in s:
            return "low"
        if s.endswith("/auth/drive") or any(k in s for k in ("mail.google.com", "gmail.modify", "gmail.send", "gmail.compose", "gmail.insert", "gmail.settings", "/auth/admin", "admin.directory", "cloud-platform")):
            return "high"
        return "medium"
    if s in ("openid", "profile", "email", "offline_access", "user.read", "user.readbasic.all"):
        return "low"
    if s.startswith("directory.read") and "write" not in s:
        return "medium"
    if any(k in s for k in ("readwrite", "write", "send", "fullcontrol", "full_access", "directory.", "manage")):
        return "high"
    return "medium"


def risk_for(scopes, source: str) -> str:
    """How much the app can do: 'high', 'medium', or 'low' (sign-in only, or nothing recorded)."""
    best = "low"
    for sc in scopes or []:
        r = scope_risk(sc, source)
        if RANK[r] > RANK[best]:
            best = r
    return best


def scope_label(scope: str, source: str) -> str:
    s = str(scope or "").strip().lower()
    if scope_risk(scope, source) == "low":
        return "Sign in (name and email)" if source == "google" else "Sign in and basic profile"
    if source == "google" and s.endswith("/auth/drive"):
        return "Full access to Google Drive"
    for key, label in (_GOOGLE_LABELS if source == "google" else _MICROSOFT_LABELS):
        if key in s:
            return label
    return (s.rsplit("/auth/", 1)[-1] if source == "google" else str(scope)).replace(".", " ").replace("_", " ")[:80]


def highlights(scopes, source: str, limit: int = 3) -> list:
    """What the access means in plain words: the most powerful things first, each once."""
    ranked = sorted(set(scopes or []), key=lambda sc: (-RANK[scope_risk(sc, source)], sc))
    out = []
    for sc in ranked:
        label = scope_label(sc, source)
        if label not in out:
            out.append(label)
    return out[:limit]


def google_records(per_user: dict) -> list:
    """per_user: email -> the token items Google returned for that person. One record per app (client id), with everyone who authorized it."""
    apps = {}
    for email, items in per_user.items():
        for t in items or []:
            cid = clean(t.get("clientId"))
            if not cid:
                continue
            a = apps.setdefault(cid, {"source": "google", "external_id": cid, "name": clean(t.get("displayText")) or cid, "publisher": None, "scopes": set(), "users": set(),
                                      "all_users": False, "kind": "web", "homepage": None, "created": None})
            a["users"].add(str(email).lower())
            a["scopes"].update(s for s in (t.get("scopes") or []) if isinstance(s, str))
            if t.get("nativeApp"):
                a["kind"] = "native"
    return _finish(apps.values())


def microsoft_records(sps, grants, users, tenant_id=None) -> list:
    """The apps someone consented to: only apps with at least one grant, never Microsoft's own, and your own tenant's apps marked 'internal'."""
    by_id = {sp.get("id"): sp for sp in sps if sp.get("id")}
    email_of = {u.get("id"): str(u.get("mail") or u.get("userPrincipalName") or "").strip().lower() for u in users}
    tenant = str(tenant_id or "").lower()
    apps = {}
    for g in grants:
        sp = by_id.get(g.get("clientId"))
        if not sp:
            continue
        owner = str(sp.get("appOwnerOrganizationId") or "").lower()
        if owner in MICROSOFT_OWNER_TENANTS:
            continue
        a = apps.setdefault(sp["id"], {"source": "microsoft", "external_id": sp["id"], "name": clean(sp.get("displayName")) or sp["id"],
                                       "publisher": clean((sp.get("verifiedPublisher") or {}).get("displayName") or sp.get("publisherName")), "scopes": set(), "users": set(),
                                       "all_users": False, "kind": "internal" if tenant and owner == tenant else "third_party", "homepage": clean(sp.get("homepage"), 512),
                                       "created": sp.get("createdDateTime")})
        a["scopes"].update(str(g.get("scope") or "").split())
        if g.get("consentType") == "AllPrincipals":
            a["all_users"] = True
        elif email_of.get(g.get("principalId")):
            a["users"].add(email_of[g["principalId"]])
    return _finish(apps.values())


def _finish(apps) -> list:
    out = []
    for a in apps:
        scopes = sorted(a["scopes"])
        out.append({**a, "scopes": scopes, "users": sorted(a["users"]), "risk": risk_for(scopes, a["source"]), "highlights": highlights(scopes, a["source"])})
    return sorted(out, key=lambda r: (-RANK[r["risk"]], -len(r["users"]), r["name"].lower()))
