"""
Creates all DB tables if they don't already exist.
Safe to run on every deploy - won't drop or modify existing tables.
"""
import asyncio
from sqlalchemy import text
from app.db.session import engine, Base
import app.models  # noqa: F401
import app.models.connector_config  # noqa: F401  (Integration Library table)
import app.models.reclamation  # noqa: F401  (License reclamation tables)

# create_all never alters an existing table, so columns added after a table first shipped go here.
# Every statement is idempotent and safe to run on each deploy.
MIGRATIONS = [
    "ALTER TABLE reclamation_workflows ADD COLUMN IF NOT EXISTS ask_users_slack BOOLEAN DEFAULT FALSE",
    "ALTER TABLE reclamation_workflows ADD COLUMN IF NOT EXISTS ask_users_per_run INTEGER DEFAULT 25",
    "ALTER TABLE reclamation_items ADD COLUMN IF NOT EXISTS asked_at TIMESTAMP WITH TIME ZONE",
]


async def main():
    print("Creating database tables (if not exists)...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        for statement in MIGRATIONS:
            await conn.execute(text(statement))
    print("Done.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
