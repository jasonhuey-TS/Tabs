"""
IntegrationSettingsService — reads/writes integration credentials from the DB
and provides a test_connection() method for each provider.
"""
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.integration_setting import IntegrationSetting, IntegrationProvider
from app.core.encryption import encrypt, decrypt

log = structlog.get_logger()


class IntegrationSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, provider: IntegrationProvider) -> IntegrationSetting | None:
        result = await self.db.execute(
            select(IntegrationSetting).where(IntegrationSetting.provider == provider)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[IntegrationSetting]:
        result = await self.db.execute(select(IntegrationSetting))
        return list(result.scalars().all())

    # ── Okta ──────────────────────────────────────────────────────────────────

    async def save_okta(self, domain: str, api_token: str, sync_interval_hours: int = 6) -> IntegrationSetting:
        setting = await self.get(IntegrationProvider.OKTA)
        if not setting:
            setting = IntegrationSetting(provider=IntegrationProvider.OKTA)
            self.db.add(setting)

        setting.okta_domain = domain.strip().rstrip("/")
        setting.okta_api_token_encrypted = encrypt(api_token)
        setting.sync_interval_hours = sync_interval_hours
        await self.db.flush()
        return setting

    def get_okta_token(self, setting: IntegrationSetting) -> str | None:
        if not setting.okta_api_token_encrypted:
            return None
        return decrypt(setting.okta_api_token_encrypted)

    # ── Azure AD ──────────────────────────────────────────────────────────────

    async def save_azure(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        sync_interval_hours: int = 6,
    ) -> IntegrationSetting:
        setting = await self.get(IntegrationProvider.AZURE_AD)
        if not setting:
            setting = IntegrationSetting(provider=IntegrationProvider.AZURE_AD)
            self.db.add(setting)

        setting.azure_tenant_id = tenant_id.strip()
        setting.azure_client_id = client_id.strip()
        setting.azure_client_secret_encrypted = encrypt(client_secret)
        setting.sync_interval_hours = sync_interval_hours
        await self.db.flush()
        return setting

    def get_azure_secret(self, setting: IntegrationSetting) -> str | None:
        if not setting.azure_client_secret_encrypted:
            return None
        return decrypt(setting.azure_client_secret_encrypted)

    # ── Enable / disable ──────────────────────────────────────────────────────

    async def set_enabled(self, provider: IntegrationProvider, enabled: bool) -> IntegrationSetting | None:
        setting = await self.get(provider)
        if setting:
            setting.is_enabled = enabled
            await self.db.flush()
        return setting

    # ── Test connections ──────────────────────────────────────────────────────

    async def test_okta(self, setting: IntegrationSetting) -> tuple[bool, str]:
        """Try listing one app from Okta. Returns (success, message)."""
        from app.integrations.okta.client import OktaClient
        token = self.get_okta_token(setting)
        if not token or not setting.okta_domain:
            return False, "Domain and API token are required."
        try:
            async with OktaClient(domain=setting.okta_domain, api_token=token) as client:
                # Just fetch one page — if it works, credentials are valid
                apps = await client._paginate("/apps", params={"limit": 1})
            msg = f"Connected — found apps in your Okta org."
            return True, msg
        except Exception as exc:
            return False, str(exc)

    async def test_azure(self, setting: IntegrationSetting) -> tuple[bool, str]:
        """Try listing one service principal from Azure AD."""
        from app.integrations.azure_ad.client import AzureADClient
        secret = self.get_azure_secret(setting)
        if not all([setting.azure_tenant_id, setting.azure_client_id, secret]):
            return False, "Tenant ID, Client ID, and Client Secret are all required."
        try:
            async with AzureADClient(
                tenant_id=setting.azure_tenant_id,
                client_id=setting.azure_client_id,
                client_secret=secret,
            ) as client:
                await client._paginate("/servicePrincipals", params={"$top": 1})
            return True, "Connected — Azure AD credentials verified."
        except Exception as exc:
            return False, str(exc)

    async def record_test_result(
        self, setting: IntegrationSetting, ok: bool, error: str | None = None
    ) -> None:
        setting.last_tested_at = datetime.now(timezone.utc)
        setting.last_test_ok = ok
        setting.last_test_error = error[:500] if error else None
        await self.db.flush()
