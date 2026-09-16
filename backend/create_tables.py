"""
Startup script that creates all DB tables directly from SQLAlchemy models.
Used in production instead of Alembic migrations since we have no migration files.
"""
import asyncio
from app.db.session import engine, Base
import app.models  # noqa: F401 — imports all models so Base knows about them


async def main():
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Done — all tables created.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
