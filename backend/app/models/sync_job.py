import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Enum, Integer, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class SyncSource(str, enum.Enum):
    OKTA = "okta"
    AZURE_AD = "azure_ad"
    CSV = "csv"


class SyncJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"   # completed with some errors


class SyncJob(Base):
    """Audit log for every data sync attempt."""
    __tablename__ = "sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[SyncSource] = mapped_column(Enum(SyncSource), nullable=False, index=True)
    status: Mapped[SyncJobStatus] = mapped_column(Enum(SyncJobStatus), default=SyncJobStatus.PENDING)

    # Counts
    apps_discovered: Mapped[int] = mapped_column(Integer, default=0)
    apps_created: Mapped[int] = mapped_column(Integer, default=0)
    apps_updated: Mapped[int] = mapped_column(Integer, default=0)
    users_synced: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    error_detail: Mapped[dict | None] = mapped_column(JSONB)   # list of error messages
    meta: Mapped[dict | None] = mapped_column(JSONB)           # source-specific metadata

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
