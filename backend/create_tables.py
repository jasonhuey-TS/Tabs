"""
Creates all DB tables if they don't already exist.
Safe to run on every deploy - won't drop or modify existing tables.
"""
import asyncio
from app.db.session import engine, Base
import app.models  # noqa: F401
import app.models.connector_config  # noqa: F401  (Integration Library table)


async def main():
    print("Creating database tables (if not exists)...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    print("Done.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
