"""The Ask Tab assistant: starter reports and plain-English questions. Read-only."""
from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    return AssistantService(db).status()


@router.post("/run")
async def run_report(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    """Run one of the built-in reports directly (no AI involved)."""
    return await AssistantService(db).run(str(payload.get("tool") or ""), payload.get("args"))


@router.post("/chat")
async def chat(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    return await AssistantService(db).chat(payload.get("messages"))
