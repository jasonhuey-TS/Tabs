"""
Integration Library - connector framework
=========================================

A *connector* teaches Tab how to read one vendor's user list (license type, last
login, account status) and writes it onto the people Okta says are assigned to
the matching app. Okta stays the source of truth for WHO has the app; the
connector adds what Okta cannot know: which license tier they hold and when
they were last active.

Adding a connector (about 60 lines)
-----------------------------------
1. Create backend/app/connectors/<vendor>.py
2. Subclass Connector, fill in the class attributes, implement test() and
   fetch_users(). Return one UserRecord per vendor account.
3. Decorate the class with @register and add the module name to the import line
   in connectors/__init__.py.

Everything else - the catalog card, credential form, encrypted storage, Test and
Sync buttons, the nightly schedule, the license column in the app drawer - is
generated from the class attributes. No migrations, no new endpoints, no new
React page.

    @register
    class AcmeConnector(Connector):
        key = "acme"
        name = "Acme"
        vendor = "Acme Inc"
        description = "Seat type and last login for Acme."
        provides = ("License type", "Last login")
        app_aliases = ("acme",)                      # used to suggest the target app
        fields = (Field("api_key", "API key", type="password", secret=True),)
        guide = Guide(steps=("Create an API key in Acme admin settings.",))

        async def test(self, cfg, db=None):
            ...                                      # return a short message or raise ConnectorError

        async def fetch_users(self, cfg):
            ...                                      # return [UserRecord(email=..., license_type=..., last_active_at=...)]

Use send() for HTTP calls: it retries on 429 and raises ConnectorError with a
readable message, which is shown to the admin as-is.

fetch_users() normally returns a list of UserRecord. If part of the data could not
be collected (say a premium-only field), return (records, ["short note", ...]) and
the notes are shown beside the sync result instead of failing silently.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar, Optional
from urllib.parse import urlparse

import httpx


class ConnectorError(Exception):
    """An error whose message is safe and useful to show to the admin."""


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    type: str = "text"            # "text" | "password" | "textarea"
    secret: bool = False          # secrets are never sent back to the browser
    required: bool = True
    help: str = ""
    placeholder: str = ""


@dataclass(frozen=True)
class AttributeField:
    """A per-person value a vendor integration provides beyond license and last login (e.g. Zoom's meeting totals). Shown as a filter and an optional column."""
    key: str
    label: str
    type: str = "text"            # "text" | "enum" | "number" | "date" | "bool"


@dataclass(frozen=True)
class Guide:
    steps: tuple = ()
    docs_url: str = ""


@dataclass
class UserRecord:
    email: str
    license_type: Optional[str] = None       # label shown in the app drawer, e.g. "licensed", "E5"
    last_active_at: Optional[datetime] = None
    full_name: Optional[str] = None
    active_days: Optional[list] = None       # dates the person was active (when the vendor reports them)
    attributes: Optional[dict] = None        # vendor-specific per-person values, keyed as in the connector's attribute_fields


# --------------------------------------------------------------------------- helpers

_OFFSET_NO_COLON = re.compile(r"([+-]\d{2})(\d{2})$")


def parse_dt(value) -> Optional[datetime]:
    """Parse ISO strings / epoch seconds / epoch millis into an aware UTC datetime.
    Returns None for empty values and for the 1970 'never' sentinel some APIs use."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            n = float(value)
            if n > 1e11:                       # milliseconds
                n /= 1000.0
            dt = datetime.fromtimestamp(n, tz=timezone.utc)
        else:
            s = str(value).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            s = _OFFSET_NO_COLON.sub(r"\1:\2", s)
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    return None if dt.year <= 1970 else dt


def as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def match_records(records, assigned_emails: set):
    """Split vendor records into (matched, unmatched) by whether the email belongs
    to someone assigned to the app in Okta. Duplicate emails are counted once."""
    matched, unmatched, seen = [], [], set()
    for rec in records:
        email = (rec.email or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        (matched if email in assigned_emails else unmatched).append(rec)
    return matched, unmatched


def _snippet(resp) -> str:
    try:
        text = " ".join((resp.text or "").split())
    except Exception:
        text = ""
    return text[:200]


def _retry_wait(resp) -> float:
    retry_after = str(resp.headers.get("retry-after", "")).strip()
    if retry_after.isdigit():
        return float(retry_after)
    reset = str(resp.headers.get("x-rate-limit-reset", "")).strip()      # Okta
    if reset.isdigit():
        return max(1.0, float(reset) - datetime.now(timezone.utc).timestamp())
    return 5.0


async def send(client, method: str, url: str, *, retries: int = 4, max_wait: float = 90.0, **kwargs):
    """HTTP request with 429 back-off. Raises ConnectorError on any failure."""
    host = urlparse(url).netloc or url
    for attempt in range(retries):
        try:
            resp = await client.request(method, url, **kwargs)
        except Exception as exc:                   # network error, timeout, bad URL
            raise ConnectorError(f"Could not reach {host}: {exc}") from exc
        if resp.status_code == 429 and attempt < retries - 1:
            await asyncio.sleep(min(_retry_wait(resp), max_wait))
            continue
        if resp.status_code >= 400:
            raise ConnectorError(f"{host} returned {resp.status_code}: {_snippet(resp)}")
        return resp
    raise ConnectorError(f"{host} kept rate-limiting requests - try again in a few minutes.")


# --------------------------------------------------------------------------- base classes

class Connector:
    """Base class for an app connector (one vendor -> one target app)."""

    key: ClassVar[str] = ""
    name: ClassVar[str] = ""
    vendor: ClassVar[str] = ""
    description: ClassVar[str] = ""
    color: ClassVar[str] = "#4B5EDE"
    initials: ClassVar[str] = ""
    provides: ClassVar[tuple] = ()
    kind: ClassVar[str] = "app"                 # "app" | "global"
    app_aliases: ClassVar[tuple] = ()           # name fragments used to suggest the target app
    fields: ClassVar[tuple] = ()
    attribute_fields: ClassVar[tuple] = ()      # AttributeField(...) for each key a record's `attributes` may hold
    guide: ClassVar[Guide] = Guide()

    # Optional resumable state for app connectors. Before fetch_users() the service sets `state_in` to what
    # the previous sync saved; a connector that wants to keep something sets `state_out` (merged into the
    # saved state). Only one sync per connector runs at a time, so plain attributes are safe.
    state_in: Optional[dict] = None
    state_out: Optional[dict] = None

    def make_client(self):
        return httpx.AsyncClient(timeout=30.0)

    def is_configured(self, cfg: dict) -> bool:
        return all(cfg.get(f.key) for f in self.fields if f.required)

    async def test(self, cfg: dict, db=None) -> str:
        raise NotImplementedError

    async def fetch_users(self, cfg: dict):
        """Return list[UserRecord], or (list[UserRecord], list[str]) with notes."""
        raise NotImplementedError


class GlobalConnector(Connector):
    """A connector that enriches ALL apps at once (e.g. Okta sign-in activity)."""

    kind = "global"

    async def is_ready(self, db) -> bool:
        raise NotImplementedError

    async def run(self, db, state: dict, progress):
        """Return (summary: dict, new_state: dict). `progress(message, state=None)`
        persists a status line (and optionally resumable state) mid-run."""
        raise NotImplementedError
