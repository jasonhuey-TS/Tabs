"""
IntegrationSetting — persists integration credentials in the database.

Sensitive values (API tokens, client secrets) are encrypted at rest using
Fernet symmetric encryption keyed from SECRET_KEY. This means even if
someone gets a DB dump, they can't use the tokens without the app's key.
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, Boolean, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class IntegrationProvider(str, enum.Enum):
    OKTA = "okta"
    AZURE_AD = "azure_ad"


class IntegrationSetting(Base):
    __tablename__ = "integration_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider), nullable=False, unique=True, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Okta fields
    okta_domain: Mapped[str | None] = mapped_column(String(255))
    okta_api_token_encrypted: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted

    # Azure AD fields
    azure_tenant_id: Mapped[str | None] = mapped_column(String(255))
    azure_client_id: Mapped[str | None] = mapped_column(String(255))
    azure_client_secret_encrypted: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted

    # Sync schedule
    sync_interval_hours: Mapped[int] = mapped_column(default=6)

    # Last test result
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_error: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
