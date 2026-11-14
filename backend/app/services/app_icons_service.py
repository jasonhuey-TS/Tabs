"""App icons: fetched once by the server, kept in the database, and served from our own address.

Why the server and not the browser: icons then load fast and identically for everyone, the list of SaaS apps you use
isn't announced to third-party sites by every person's browser, and nothing is blocked by a content policy.

Because the server makes the requests, it is careful about WHAT it fetches: https only, never an internal address
(a website field someone typed in must not be able to point the server at your network), only real raster images
(an SVG can carry scripts), and a size limit. Sources, in order: the logo Okta supplied, then the site's favicon.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin, urlparse

import httpx
from sqlalchemy import select

from app.models import App
from app.models.app_extras import AppIcon, AppSetting
from app.services.reclamation_service import parse_uuid

MAX_BYTES = 200_000
MAX_REDIRECTS = 3
TIMEOUT = 5.0
RETRY_AFTER = timedelta(days=7)
FAVICON = "https://www.google.com/s2/favicons?domain={domain}&sz=128"
_gate = asyncio.Semaphore(6)                         # at most a few lookups at once, however many icons a page asks for


def sniff_image(data: bytes):
    """Content type from the file's own first bytes (never trust the server's label), or None. SVG is refused on purpose."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    return None


def safe_url(url) -> bool:
    try:
        p = urlparse(str(url))
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.hostname) and "@" not in (p.netloc or "") and p.port in (None, 443)


def _public(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified)


def resolve(host: str) -> list:
    try:
        return [i[4][0] for i in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]
    except OSError:
        return []


def host_is_public(host: str, resolver=resolve) -> bool:
    """True only if the name resolves, and every address it resolves to is a public one."""
    try:
        ipaddress.ip_address(host)
        return _public(host)
    except ValueError:
        pass
    addresses = resolver(host)
    return bool(addresses) and all(_public(a) for a in addresses)


def favicon_url(website):
    """The favicon-service URL for a website, or None if it doesn't look like a real public site."""
    text = (website or "").strip()
    if not text:
        return None
    host = (urlparse(text if "://" in text else "https://" + text).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if "." not in host or host.endswith(".local") or host.endswith(".internal"):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    return FAVICON.format(domain=quote(host, safe=""))


async def fetch_image(client, url: str, resolver=resolve, max_bytes: int = MAX_BYTES):
    """(bytes, content_type) for a safe, small, real image at `url`, following a few redirects by hand; otherwise None."""
    loop = asyncio.get_running_loop()
    for _ in range(MAX_REDIRECTS + 1):
        if not safe_url(url):
            return None
        host = urlparse(url).hostname
        if not await loop.run_in_executor(None, lambda: host_is_public(host, resolver)):
            return None
        async with client.stream("GET", url) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    return None
                url = urljoin(url, location)
                continue
            if resp.status_code != 200:
                return None
            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    return None
            kind = sniff_image(bytes(body))
            return (bytes(body), kind) if kind else None
    return None


class AppIconService:
    def __init__(self, db):
        self.db = db

    def _client(self):
        return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "Tab-icon-fetch/1.0"})

    async def get(self, app_id: str, resolver=resolve, force: bool = False):
        """(bytes, content_type) or None. Looks up the network at most once per app per week (unless forced, as when someone clicks 'look up missing icons')."""
        app_uuid = parse_uuid(app_id)
        if app_uuid is None:
            return None
        row = (await self.db.execute(select(AppIcon).where(AppIcon.app_id == app_uuid))).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row is not None and row.data:
            return row.data, row.content_type
        if not force and row is not None and row.failed_at is not None and now - _aware(row.failed_at) < RETRY_AFTER:
            return None
        app = (await self.db.execute(select(App.logo_url, App.website, AppSetting.website).select_from(App).outerjoin(AppSetting, AppSetting.app_id == App.id).where(App.id == app_uuid))).first()
        if app is None:
            return None
        logo, site, typed = (list(app) + [None, None])[:3]
        found, source, tried = None, None, set()
        async with _gate:
            async with self._client() as client:
                # the logo Okta supplied, then the favicon of the website someone entered (or Zylo supplied) on the app, then the app's own website field
                for label, url in (("logo", logo), ("favicon", favicon_url(typed)), ("favicon", favicon_url(site))):
                    if not url or url in tried:
                        continue
                    tried.add(url)
                    try:
                        found = await fetch_image(client, url, resolver)
                    except Exception:
                        found = None
                    if found:
                        source = label
                        break
        if row is None:
            row = AppIcon(app_id=app_uuid)
            self.db.add(row)
        if found:
            row.data, row.content_type, row.source, row.fetched_at, row.failed_at = found[0], found[1], source, now, None
        else:
            row.data, row.content_type, row.source, row.failed_at = None, None, None, now
        await self.db.commit()
        return found

    async def _sources(self):
        """Every app with what an icon could be looked up from, and what is already stored: [(id, name, has_source, has_icon, tried_and_failed)]."""
        apps = (await self.db.execute(select(App.id, App.name, App.logo_url, App.website, AppSetting.website).select_from(App).outerjoin(AppSetting, AppSetting.app_id == App.id))).all()
        icons = {i: (bool(d), f) for i, d, f in (await self.db.execute(select(AppIcon.app_id, AppIcon.data, AppIcon.failed_at))).all()}
        out = []
        for app_id, name, logo, site, typed in apps:
            has_icon, failed = icons.get(app_id, (False, None))
            out.append((app_id, name, bool(logo or favicon_url(typed) or favicon_url(site)), has_icon, failed is not None and not has_icon))
        return out

    async def summary(self) -> dict:
        """Where icons stand: how many apps have one, and for the rest, why not."""
        rows = await self._sources()
        with_icon = sum(1 for r in rows if r[3])
        rest = [r for r in rows if not r[3]]
        return {"total": len(rows), "with_icon": with_icon, "no_source": sum(1 for r in rest if not r[2]), "failed": sum(1 for r in rest if r[2] and r[4]),
                "not_tried": sum(1 for r in rest if r[2] and not r[4])}

    async def fetch_missing(self, retry_failed: bool = True, budget_seconds: float = 25.0, limit: int = 200, resolver=resolve) -> dict:
        """Look up icons for apps that have none but could (a logo or website to go on). One at a time, stopping when the time budget is spent."""
        todo = [r for r in await self._sources() if r[2] and not r[3] and (retry_failed or not r[4])]
        todo.sort(key=lambda r: (r[4], str(r[1]).lower()))                      # apps never tried first
        started, tried, found = time.monotonic(), 0, 0
        for app_id, *_ in todo[:max(1, min(int(limit), 500))]:
            if time.monotonic() - started > budget_seconds:
                break
            tried += 1
            if await self.get(str(app_id), resolver, force=True):
                found += 1
        hint = None
        if tried >= 5 and found == 0:
            hint = ("None of the lookups worked, which usually means Tab's server can't reach the internet. Ask whoever runs the server to allow outbound HTTPS "
                    "(to www.google.com and to Okta's logo address), then try again.")
        return {"tried": tried, "found": found, "failed": tried - found, "remaining": len(todo) - tried, "hint": hint}


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt
