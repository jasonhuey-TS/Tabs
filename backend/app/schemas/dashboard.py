from pydantic import BaseModel


class RenewalUpcoming(BaseModel):
    contract_id: str
    app_name: str
    vendor: str
    end_date: str
    days_until_expiry: int
    total_value_cents: int | None
    owner_email: str | None


class SpendByCategory(BaseModel):
    category: str
    total_annual_cost_cents: int
    app_count: int


class DashboardStats(BaseModel):
    # Discovery
    total_apps: int
    managed_apps: int
    shadow_it_apps: int
    apps_added_last_30d: int

    # Spend
    total_annual_spend_cents: int
    total_waste_cents: int
    avg_utilization_pct: float | None
    spend_by_category: list[SpendByCategory]

    # Contracts
    contracts_expiring_90d: int
    contracts_expiring_30d: int
    upcoming_renewals: list[RenewalUpcoming]

    # Licenses
    total_seats_purchased: int
    total_seats_active: int
    wasted_seats: int
