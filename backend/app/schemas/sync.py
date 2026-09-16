import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.sync_job import SyncSource, SyncJobStatus


class SyncJobResponse(BaseModel):
    id: uuid.UUID
    source: SyncSource
    status: SyncJobStatus
    apps_discovered: int
    apps_created: int
    apps_updated: int
    users_synced: int
    errors: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportResponse(BaseModel):
    id: uuid.UUID
    file_name: str
    import_type: str
    rows_total: int
    rows_imported: int
    rows_skipped: int
    rows_errored: int
    errors: list | None
    created_at: datetime

    model_config = {"from_attributes": True}
