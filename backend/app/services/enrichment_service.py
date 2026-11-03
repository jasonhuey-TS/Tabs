"""
Enrichment service — pulls richer usage data from Slack and Zoom APIs
and writes last_login_at + role_in_app (license type) into app_users.
"""
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import App, AppUser, User
from app.integrations.slack.client import SlackClient, normalize_slack_user
from app.integrations.zoom.client import ZoomClient, normalize_zoom_user

log = structlog.get_logger()


class EnrichmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _find_app_by_slug(self, *slugs: str) -> App | None:
        for slug in slugs:
            result = await self.db.execute(
                select(App).where(App.vendor_slug == slug)
            )
            app = result.scalar_one_or_none()
            if app:
                return app
        return None

    async def _update_assigned_user(
        self,
        app: App,
        email: str,
        last_login_at: datetime | None,
        license_type: str | None,
    ) -> bool:
        """Update last-active / license type for a user who is ALREADY assigned
        to this app (from the Okta sync). Accounts that exist in the app but are
        not assigned in Okta are ignored, so the app's user list stays accurate.
        Returns True if a row was updated."""
        result = await self.db.execute(
            select(AppUser)
            .join(User, User.id == AppUser.user_id)
            .where(AppUser.app_id == app.id, func.lower(User.email) == email.lower())
        )
        app_user = result.scalar_one_or_none()
        if not app_user:
            return False

        if last_login_at:
            app_user.last_login_at = last_login_at
        if license_type:
            app_user.role_in_app = license_type
        return True

    # ── Slack ─────────────────────────────────────────────────────────────

    async def enrich_slack(self, bot_token: str) -> dict:
        """Pull Slack users and update last_active + license type."""
        log.info("enrich.slack.start")

        app = await self._find_app_by_slug("slack", "slack-", "slack-enterprise")
        if not app:
            return {"error": "Slack app not found in database. Run an Okta sync first."}

        try:
            async with SlackClient(bot_token=bot_token) as slack:
                # Verify token
                await slack.test_auth()

                # Pull all members
                members = await slack.list_users()
                updated = 0
                skipped = 0   # accounts not assigned to the app in Okta

                for member in members:
                    normalized = normalize_slack_user(member)
                    email = normalized.get("email", "")
                    if not email:
                        continue

                    last_active = None
                    if normalized.get("last_active_at"):
                        try:
                            last_active = datetime.fromisoformat(normalized["last_active_at"])
                        except Exception:
                            pass

                    if await self._update_assigned_user(
                        app=app,
                        email=email,
                        last_login_at=last_active,
                        license_type=normalized["license_type"],
                    ):
                        updated += 1
                    else:
                        skipped += 1

            await self.db.flush()
            log.info("enrich.slack.done", updated=updated, skipped=skipped)
            return {"ok": True, "users_updated": updated, "skipped": skipped, "app": app.name}

        except Exception as exc:
            log.error("enrich.slack.failed", error=str(exc))
            return {"error": str(exc)}

    # ── Zoom ──────────────────────────────────────────────────────────────

    async def enrich_zoom(self, account_id: str, client_id: str, client_secret: str) -> dict:
        """Pull Zoom users and update last_login_at + license type."""
        log.info("enrich.zoom.start")

        app = await self._find_app_by_slug("zoom", "zoom-video")
        if not app:
            return {"error": "Zoom app not found in database. Run an Okta sync first."}

        try:
            async with ZoomClient(
                account_id=account_id,
                client_id=client_id,
                client_secret=client_secret,
            ) as zoom:
                users = await zoom.list_all_users()
                updated = 0
                skipped = 0   # accounts not assigned to the app in Okta

                for user in users:
                    normalized = normalize_zoom_user(user)
                    email = normalized.get("email", "")
                    if not email:
                        continue

                    last_login = None
                    if normalized.get("last_login_at"):
                        try:
                            last_login = datetime.fromisoformat(normalized["last_login_at"])
                        except Exception:
                            pass

                    if await self._update_assigned_user(
                        app=app,
                        email=email,
                        last_login_at=last_login,
                        # A deactivated Zoom account does not hold a license seat.
                        license_type=(normalized["license_type"]
                                      if normalized.get("status", "active") == "active"
                                      else "inactive"),
                    ):
                        updated += 1
                    else:
                        skipped += 1

            await self.db.flush()
            log.info("enrich.zoom.done", updated=updated, skipped=skipped)
            return {"ok": True, "users_updated": updated, "skipped": skipped, "app": app.name}

        except Exception as exc:
            log.error("enrich.zoom.failed", error=str(exc))
            return {"error": str(exc)}
