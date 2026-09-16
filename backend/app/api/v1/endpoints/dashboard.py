from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import date, timedelta

from app.db.session import get_db
from app.models import App, License, Contract, AppStatus, ContractStatus
from app.schemas.dashboard import DashboardStats, SpendByCategory, RenewalUpcoming

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    # --- App counts ---
    total_apps = (await db.execute(select(func.count()).select_from(App))).scalar_one()
    managed_apps = (await db.execute(select(func.count()).select_from(App).where(App.status == AppStatus.MANAGED))).scalar_one()
    shadow_it_apps = (await db.execute(select(func.count()).select_from(App).where(App.is_shadow_it == True))).scalar_one()
    apps_added_last_30d = (await db.execute(
        select(func.count()).select_from(App).where(App.created_at >= thirty_days_ago)
    )).scalar_one()

    # --- Spend ---
    spend_result = await db.execute(
        select(
            func.sum(License.total_annual_cost_cents),
            func.sum(License.waste_cost_cents),
            func.avg(License.utilization_pct),
            func.sum(License.seats_purchased),
            func.sum(License.seats_active),
            func.sum(License.waste_seats),
        ).select_from(License)
    )
    spend_row = spend_result.one()
    total_spend = spend_row[0] or 0
    total_waste = spend_row[1] or 0
    avg_util = float(spend_row[2]) if spend_row[2] else None
    total_seats_purchased = spend_row[3] or 0
    total_seats_active = spend_row[4] or 0
    wasted_seats = spend_row[5] or 0

    # Spend by category
    cat_result = await db.execute(
        select(
            App.category,
            func.sum(License.total_annual_cost_cents).label("total"),
            func.count(App.id).label("app_count"),
        )
        .join(License, License.app_id == App.id)
        .group_by(App.category)
        .order_by(func.sum(License.total_annual_cost_cents).desc())
    )
    spend_by_category = [
        SpendByCategory(category=row.category.value, total_annual_cost_cents=row.total or 0, app_count=row.app_count)
        for row in cat_result.all()
    ]

    # --- Contracts expiring ---
    expiring_90 = (await db.execute(
        select(func.count()).select_from(Contract).where(
            Contract.status == ContractStatus.ACTIVE,
            Contract.end_date <= today + timedelta(days=90),
            Contract.end_date >= today,
        )
    )).scalar_one()
    expiring_30 = (await db.execute(
        select(func.count()).select_from(Contract).where(
            Contract.status == ContractStatus.ACTIVE,
            Contract.end_date <= today + timedelta(days=30),
            Contract.end_date >= today,
        )
    )).scalar_one()

    upcoming_result = await db.execute(
        select(Contract, App.name, App.vendor)
        .join(App, App.id == Contract.app_id)
        .where(
            Contract.status == ContractStatus.ACTIVE,
            Contract.end_date >= today,
            Contract.end_date <= today + timedelta(days=90),
        )
        .order_by(Contract.end_date.asc())
        .limit(10)
    )
    upcoming_renewals = [
        RenewalUpcoming(
            contract_id=str(row.Contract.id),
            app_name=row.name,
            vendor=row.vendor,
            end_date=row.Contract.end_date.isoformat(),
            days_until_expiry=(row.Contract.end_date - today).days,
            total_value_cents=row.Contract.total_value_cents,
            owner_email=row.Contract.owner_email,
        )
        for row in upcoming_result.all()
    ]

    return DashboardStats(
        total_apps=total_apps,
        managed_apps=managed_apps,
        shadow_it_apps=shadow_it_apps,
        apps_added_last_30d=apps_added_last_30d,
        total_annual_spend_cents=total_spend,
        total_waste_cents=total_waste,
        avg_utilization_pct=avg_util,
        spend_by_category=spend_by_category,
        contracts_expiring_90d=expiring_90,
        contracts_expiring_30d=expiring_30,
        upcoming_renewals=upcoming_renewals,
        total_seats_purchased=total_seats_purchased,
        total_seats_active=total_seats_active,
        wasted_seats=wasted_seats,
    )
