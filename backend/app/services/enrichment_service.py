"""
Enrichment service — pulls richer usage data from Slack and Zoom APIs
and writes last_login_at + role_in_app (license type) into app_users.
"""
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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

    async def _upsert_user_with_login(
        self,
        app: App,
        email: str,
        full_name: str,
        last_login_at: datetime | None,
        license_type: str | None,
    ) -> None:
        # Get or create user
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            user = User(email=email, full_name=full_name or email)
            self.db.add(user)
            await self.db.flush()

        # Get or create app_user link
        result2 = await self.db.execute(
            select(AppUser).where(AppUser.app_id == app.id, AppUser.user_id == user.id)
        )
        app_user = result2.scalar_one_or_none()
        if not app_user:
            app_user = AppUser(app_id=app.id, user_id=user.id)
            self.db.add(app_user)

        # Update with enriched data
        if last_login_at:
            app_user.last_login_at = last_login_at
        if license_type:
            app_user.role_in_app = license_type

        await self.db.flush()

    # ── Slack ─────────────────────────────────────────────────────────────

    async def enrich_slack(self, bot_token: str) -> dict:
        """Pull Slack users and update last_active + license type."""
        log.info("enrich.slack.start")

        app = await self._find_app_by_slug("slack", "slack-enterprise")
        if not app:
            return {"error": "Slack app not found in database. Run an Okta sync first."}

        try:
            async with SlackClient(bot_token=bot_token) as slack:
                # Verify token
                await slack.test_auth()

                # Pull all members
                members = await slack.list_users()
                updated = 0

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

                    await self._upsert_user_with_login(
                        app=app,
                        email=email,
                        full_name=normalized["full_name"],
                        last_login_at=last_active,
                        license_type=normalized["license_type"],
                    )
                    updated += 1

            await self.db.flush()
            log.info("enrich.slack.done", updated=updated)
            return {"ok": True, "users_updated": updated, "app": app.name}

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

                    await self._upsert_user_with_login(
                        app=app,
                        email=email,
                        full_name=normalized["full_name"],
                        last_login_at=last_login,
                        license_type=normalized["license_type"],
                    )
                    updated += 1

            await self.db.flush()
            log.info("enrich.zoom.done", updated=updated)
            return {"ok": True, "users_updated": updated, "app": app.name}

        except Exception as exc:
            log.error("enrich.zoom.failed", error=str(exc))
            return {"error": str(exc)}
