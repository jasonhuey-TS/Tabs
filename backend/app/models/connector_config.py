"""
ConnectorConfig - one row per Integration Library connector (Zoom, Slack, ...).

Credentials are stored as a single Fernet-encrypted JSON blob, so adding a new
connector (or a new credential field) never needs a database migration.
This table is created automatically by create_tables.py.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class ConnectorConfig(Base):
    __tablename__ = "connector_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    config_encrypted: Mapped[str | None] = mapped_column(Text)          # encrypted JSON of all fields
    target_app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_message: Mapped[str | None] = mapped_column(Text)

    sync_status: Mapped[str | None] = mapped_column(String(16))         # running | ok | error
    last_sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_message: Mapped[str | None] = mapped_column(Text)
    sync_summary: Mapped[dict | None] = mapped_column(JSON)
    state: Mapped[dict | None] = mapped_column(JSON)                    # connector-private (e.g. log cursor)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
