"""App icons, served from our own address."""
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.app_icons_service import AppIconService

router = APIRouter(prefix="/app-icons", tags=["app-icons"])

# The image is shown in an <img>; these headers also make it harmless if someone opens the URL directly.
SAFE = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"}


@router.get("/{app_id}")
async def app_icon(app_id: str, db: AsyncSession = Depends(get_db)):
    found = await AppIconService(db).get(app_id)
    if found is None:
        return Response(status_code=404, headers={**SAFE, "Cache-Control": "public, max-age=3600"})   # the browser won't re-ask for an hour
    data, content_type = found
    return Response(content=data, media_type=content_type, headers={**SAFE, "Cache-Control": "public, max-age=86400"})
