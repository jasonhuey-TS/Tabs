import asyncio
from app.db.session import engine, Base
import app.models

async def main():
    print("Creating tables if not exist...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    print("Done.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
