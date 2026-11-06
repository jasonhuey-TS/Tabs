"""
Slack DMs that ask a person whether they still need a license, plus the signed links behind the buttons.

The buttons are plain link buttons that open a page on this app, so no Slack interactivity setup or
signing secret is needed. Each link carries a signed, expiring token for ONE review item:

    <item id>.<expires at>.<signature>      signature = HMAC-SHA256(SECRET_KEY, "<item id>.<expires at>")

The token only identifies the item. What it can do is limited by the endpoint: "keep" is applied at
once, "release" needs a second confirming click, and nothing is ever removed from Okta.

Slack bot scopes needed: users:read, users:read.email (look up the person) and chat:write (send the DM).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta

TOKEN_TTL_DAYS = 30
INSECURE_SECRETS = {"", "change-me-in-production"}
MIN_SECRET_LENGTH = 16
SLACK_API = "https://slack.com/api"

# Slack errors that mean "stop, nothing else will work" rather than "this one person failed".
FATAL_ERRORS = {"invalid_auth", "not_authed", "account_inactive", "token_revoked", "token_expired",
                "missing_scope", "no_permission", "org_login_required"}


def secret_is_safe(secret) -> bool:
    return bool(secret) and secret not in INSECURE_SECRETS and len(secret) >= MIN_SECRET_LENGTH


def _sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()[:40]


def make_token(secret: str, item_id: str, now: datetime, ttl_days: int = TOKEN_TTL_DAYS) -> str:
    expires = int((now + timedelta(days=ttl_days)).timestamp())
    message = f"{item_id}.{expires}"
    return f"{message}.{_sign(secret, message)}"


def verify_token(secret: str, token: str, now: datetime):
    """Return (item_id, None) for a good token, else (None, "invalid" | "expired")."""
    parts = (token or "").split(".")
    if len(parts) != 3 or not secret_is_safe(secret):
        return None, "invalid"
    item_id, expires, signature = parts
    if not hmac.compare_digest(signature, _sign(secret, f"{item_id}.{expires}")):
        return None, "invalid"
    try:
        if now.timestamp() > int(expires):
            return None, "expired"
    except ValueError:
        return None, "invalid"
    return item_id, None


def first_name(full_name, email) -> str:
    name = (full_name or "").strip()
    if name and "@" not in name:
        return name.split()[0]
    local = (email or "").split("@")[0].replace(".", " ").replace("_", " ").strip()
    return local.split()[0].capitalize() if local else "there"


def _esc(text) -> str:
    """Slack mrkdwn escaping."""
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(first: str, app_name: str, days: int | None, last_active: datetime | None,
                  keep_url: str, release_url: str):
    """Return (fallback_text, blocks) for the DM."""
    if last_active is not None:
        when = f"You last signed in on {last_active.strftime('%b %-d, %Y')}."
    elif days is not None:
        when = f"I don't see a sign-in from you in the last {max(days, 1)} days."
    else:
        when = "I don't see any recent sign-in from you."
    app = _esc(app_name)
    body = (f"Hi {_esc(first)} :wave:\n\nYou have a *{app}* license, and it doesn't look like it's been used lately. "
            f"{when}\n\nDo you still need it? If not, giving it up lets IT reassign the license to someone else — "
            f"you can always request access again later.")
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Yes, I still need it"},
             "style": "primary", "url": keep_url},
            {"type": "button", "text": {"type": "plain_text", "text": "Reclaim my license"}, "url": release_url},
        ]},
    ]
    return f"Do you still need your {app_name} license?", blocks


class SlackDM:
    """Minimal Slack Web API calls, given an httpx-style client. Methods return (value, error_code)."""

    def __init__(self, bot_token: str):
        self.headers = {"Authorization": f"Bearer {bot_token}"}

    async def _call(self, client, method: str, *, params=None, json=None):
        for attempt in (0, 1):
            if json is None:
                resp = await client.get(f"{SLACK_API}/{method}", params=params, headers=self.headers)
            else:
                resp = await client.post(f"{SLACK_API}/{method}", json=json, headers=self.headers)
            if resp.status_code == 429 and attempt == 0:
                try:
                    wait = min(float(resp.headers.get("Retry-After", "2")), 10.0)
                except (TypeError, ValueError):
                    wait = 2.0
                await asyncio.sleep(wait)
                continue
            if resp.status_code == 429:
                return None, "rate_limited"
            if resp.status_code >= 300:
                return None, f"http_{resp.status_code}"
            try:
                data = resp.json()
            except ValueError:
                return None, "bad_response"
            return (data, None) if data.get("ok") else (None, data.get("error") or "unknown_error")
        return None, "rate_limited"

    async def user_id(self, client, email: str):
        data, err = await self._call(client, "users.lookupByEmail", params={"email": email})
        return ((data.get("user") or {}).get("id"), None) if data else (None, err)

    async def send(self, client, user_id: str, text: str, blocks: list):
        # Posting to a user ID delivers the message as a DM from the bot (needs only chat:write).
        data, err = await self._call(client, "chat.postMessage",
                                     json={"channel": user_id, "text": text, "blocks": blocks, "unfurl_links": False})
        return (True, None) if data else (False, err)
