from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models import Contract, App
from app.schemas.contract import ContractCreate, ContractUpdate, ContractResponse
from app.services.alert_service import AlertService

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("", response_model=list[ContractResponse])
async def list_contracts(
    app_id: UUID | None = None,
    status: str | None = None,
    expiring_within_days: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    from datetime import date, timedelta
    q = select(Contract)
    if app_id:
        q = q.where(Contract.app_id == app_id)
    if status:
        q = q.where(Contract.status == status)
    if expiring_within_days is not None:
        cutoff = date.today() + timedelta(days=expiring_within_days)
        q = q.where(Contract.end_date <= cutoff, Contract.end_date >= date.today())
    q = q.order_by(Contract.end_date.asc().nullslast())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(payload: ContractCreate, db: AsyncSession = Depends(get_db)):
    app_result = await db.execute(select(App).where(App.id == payload.app_id))
    if not app_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="App not found")
    contract = Contract(**payload.model_dump())
    db.add(contract)
    await db.flush()
    # Schedule renewal alerts
    alert_service = AlertService(db)
    await alert_service.schedule_alerts_for_contract(contract)
    return contract


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(contract_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(contract_id: UUID, payload: ContractUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contract, field, value)
    await db.flush()
    return contract


@router.post("/{contract_id}/upload", response_model=ContractResponse)
async def upload_contract_file(
    contract_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a contract PDF to S3 and attach it to the contract record."""
    import boto3
    from app.core.config import settings

    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    key = f"contracts/{contract_id}/{file.filename}"
    content = await file.read()

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content, ContentType=file.content_type)

    contract.file_key = key
    contract.file_name = file.filename
    await db.flush()
    return contract
