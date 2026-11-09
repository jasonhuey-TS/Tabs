"""
License reclamation API: analytics on inactive assignments, workflows, and the review queue.

Mutations use POST (the web client only issues GET/POST). Expected problems return
{"ok": false, "message": ...} so the UI can show the reason.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import response_page
from app.services.reclamation_service import MAX_DAYS, MIN_DAYS, ReclamationService

router = APIRouter(prefix="/reclamation", tags=["reclamation"])


class WorkflowIn(BaseModel):
    name: str
    app_id: Optional[str] = None
    inactivity_days: int = 60
    min_savings_usd: float = 0
    notify_slack: bool = False
    webhook_url: Optional[str] = None
    clear_webhook: bool = False
    auto_run: bool = False
    ask_users_slack: bool = False
    ask_users_per_run: int = 25
    public_base_url: Optional[str] = None
    is_enabled: bool = True


class AppModeIn(BaseModel):
    mode: str            # trusted | ignored | default


class AskIn(BaseModel):
    ids: List[str]


class DecideIn(BaseModel):
    ids: List[str]
    action: str          # approve | keep | dismiss | reopen


def _csv(text: str, filename: str) -> Response:
    return Response(content=text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ------------------------------------------------------------------ analytics

@router.get("/overview")
async def overview(days: int = Query(60, ge=MIN_DAYS, le=MAX_DAYS), db: AsyncSession = Depends(get_db)):
    svc = ReclamationService(db)
    data = await svc.overview(days)
    data["stats"] = await svc.stats()
    return data


@router.get("/inactive")
async def inactive(days: int = Query(60, ge=MIN_DAYS, le=MAX_DAYS), app_id: Optional[str] = None,
                   include_untracked: bool = False, limit: int = Query(100, ge=1, le=500),
                   offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    return await ReclamationService(db).inactive(days, app_id, include_untracked, limit, offset)


_BUCKET = "^(d7|d30|d60|d90|none)$"


@router.get("/activity")
async def activity(bucket: Optional[str] = Query(None, pattern=_BUCKET),
                   inactive_days: Optional[int] = Query(None, ge=MIN_DAYS, le=MAX_DAYS),
                   app_id: Optional[str] = None, email: Optional[str] = None, q: Optional[str] = Query(None, max_length=100),
                   sort: str = Query("oldest", pattern="^(oldest|newest)$"),
                   limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    """Who has / hasn't been active: the data behind every clickable number on the Opportunities tab."""
    return await ReclamationService(db).activity(bucket=bucket, inactive_days=inactive_days, app_id=app_id, email=email,
                                                 q=q, sort=sort, limit=limit, offset=offset)


@router.get("/activity.csv")
async def activity_csv(bucket: Optional[str] = Query(None, pattern=_BUCKET),
                       inactive_days: Optional[int] = Query(None, ge=MIN_DAYS, le=MAX_DAYS),
                       app_id: Optional[str] = None, email: Optional[str] = None, q: Optional[str] = Query(None, max_length=100),
                       sort: str = Query("oldest", pattern="^(oldest|newest)$"), db: AsyncSession = Depends(get_db)):
    return _csv(await ReclamationService(db).activity_csv(bucket=bucket, inactive_days=inactive_days, app_id=app_id,
                                                          email=email, q=q, sort=sort), "activity.csv")


@router.get("/inactive.csv")
async def inactive_csv(days: int = Query(60, ge=MIN_DAYS, le=MAX_DAYS), app_id: Optional[str] = None,
                       include_untracked: bool = False, db: AsyncSession = Depends(get_db)):
    return _csv(await ReclamationService(db).inactive_csv(days, app_id, include_untracked),
                f"inactive-assignments-{days}d.csv")


@router.post("/apps/{app_id}/mode")
async def set_app_mode(app_id: str, payload: AppModeIn, db: AsyncSession = Depends(get_db)):
    """Trust Okta sign-ins for an app, ignore it, or reset to the default (vendor activity only)."""
    ok, message = await ReclamationService(db).set_app_mode(app_id, payload.mode)
    return {"ok": ok, "message": message}


# ------------------------------------------------------------------ workflows

@router.get("/workflows")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    return await ReclamationService(db).list_workflows()


@router.post("/workflows")
async def create_workflow(payload: WorkflowIn, db: AsyncSession = Depends(get_db)):
    ok, message, wf_id = await ReclamationService(db).save_workflow(payload.model_dump())
    return {"ok": ok, "message": message, "id": wf_id}


@router.post("/workflows/{wf_id}")
async def update_workflow(wf_id: str, payload: WorkflowIn, db: AsyncSession = Depends(get_db)):
    ok, message, new_id = await ReclamationService(db).save_workflow(payload.model_dump(), wf_id)
    return {"ok": ok, "message": message, "id": new_id}


@router.post("/workflows/{wf_id}/enabled")
async def set_enabled(wf_id: str, enabled: bool = True, db: AsyncSession = Depends(get_db)):
    if not await ReclamationService(db).set_enabled(wf_id, enabled):
        raise HTTPException(status_code=404, detail="Unknown workflow")
    return {"ok": True}


@router.post("/workflows/{wf_id}/delete")
async def delete_workflow(wf_id: str, db: AsyncSession = Depends(get_db)):
    if not await ReclamationService(db).delete_workflow(wf_id):
        raise HTTPException(status_code=404, detail="Unknown workflow")
    return {"ok": True}


@router.post("/workflows/{wf_id}/run")
async def run_workflow(wf_id: str, db: AsyncSession = Depends(get_db)):
    return await ReclamationService(db).run_workflow(wf_id, trigger="manual")


# ------------------------------------------------------------------ review queue

@router.get("/items")
async def list_items(status: Optional[str] = None, workflow_id: Optional[str] = None, app_id: Optional[str] = None,
                     limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                     db: AsyncSession = Depends(get_db)):
    return await ReclamationService(db).list_items(status, workflow_id, app_id, limit, offset)


@router.get("/items.csv")
async def items_csv(status: str = "approved", db: AsyncSession = Depends(get_db)):
    return _csv(await ReclamationService(db).items_csv(status), f"reclamation-{status}.csv")


@router.post("/items/decide")
async def decide(payload: DecideIn, db: AsyncSession = Depends(get_db)):
    return await ReclamationService(db).decide(payload.ids, payload.action)


@router.post("/items/ask")
async def ask_in_slack(payload: AskIn, db: AsyncSession = Depends(get_db)):
    """Send the 'do you still need this?' Slack message to the people on the selected items."""
    return await ReclamationService(db).ask_items(payload.ids)


# ------------------------------------------------------------------ public: the Slack buttons land here

@router.get("/respond", response_class=HTMLResponse, include_in_schema=False)
async def respond(token: str = "", answer: str = "", confirm: int = 0, db: AsyncSession = Depends(get_db)):
    """Opened from the buttons in the Slack message. The signed token identifies the item; it is not a login."""
    result = await ReclamationService(db).respond(token, answer, confirm=bool(confirm))
    status, html = response_page.render(result, token)
    return HTMLResponse(content=html, status_code=status, headers={"Cache-Control": "no-store"})
