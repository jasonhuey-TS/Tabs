"""
CSV import service — parses uploaded files and upserts apps, licenses, or contracts.

Expected CSV columns by import type:

apps.csv:
  name, vendor, category, status, owner_email, department, website

licenses.csv:
  app_name (or vendor_slug), license_type, seats_purchased,
  cost_per_seat_cents, total_annual_cost_cents, currency, billing_cycle

contracts.csv:
  app_name (or vendor_slug), start_date, end_date, auto_renews,
  cancellation_notice_days, total_value_cents, currency, owner_email, notes
"""
import csv
import io
import uuid
import structlog
from datetime import datetime, timezone, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import App, License, Contract, ImportRecord, AppCategory, AppStatus
from app.models.license import LicenseType
from app.models.contract import ContractStatus

log = structlog.get_logger()

DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _safe_int(s: str) -> int | None:
    try:
        return int(s.strip()) if s.strip() else None
    except (ValueError, AttributeError):
        return None


class ImportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_csv(
        self,
        content: bytes,
        import_type: str,
        file_name: str,
        uploaded_by_id: uuid.UUID | None = None,
    ) -> ImportRecord:
        record = ImportRecord(
            file_name=file_name,
            import_type=import_type,
            uploaded_by_id=uploaded_by_id,
        )
        self.db.add(record)

        text = content.decode("utf-8-sig")  # handle BOM
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        record.rows_total = len(rows)

        errors = []
        for i, row in enumerate(rows, start=2):  # row 1 is header
            try:
                if import_type == "apps":
                    await self._import_app_row(row)
                elif import_type == "licenses":
                    await self._import_license_row(row)
                elif import_type == "contracts":
                    await self._import_contract_row(row)
                else:
                    raise ValueError(f"Unknown import_type: {import_type}")
                record.rows_imported += 1
            except Exception as exc:
                log.warning("import.row_error", row=i, error=str(exc))
                errors.append({"row": i, "message": str(exc)})
                record.rows_errored += 1

        record.errors = errors if errors else None
        await self.db.flush()
        return record

    async def _import_app_row(self, row: dict) -> App:
        name = row.get("name", "").strip()
        vendor = row.get("vendor", "").strip() or name
        if not name:
            raise ValueError("name is required")

        vendor_slug = vendor.lower().replace(" ", "-")
        result = await self.db.execute(select(App).where(App.vendor_slug == vendor_slug))
        app = result.scalar_one_or_none()
        if not app:
            app = App(
                name=name,
                vendor=vendor,
                vendor_slug=vendor_slug,
                category=AppCategory(row.get("category", "other").lower()) if row.get("category") else AppCategory.OTHER,
                status=AppStatus(row.get("status", "unmanaged").lower()) if row.get("status") else AppStatus.UNMANAGED,
                owner_email=row.get("owner_email") or None,
                department=row.get("department") or None,
                website=row.get("website") or None,
                discovered_via="csv",
            )
            self.db.add(app)
        await self.db.flush()
        return app

    async def _import_license_row(self, row: dict) -> License:
        vendor_slug = (row.get("vendor_slug") or row.get("app_name", "")).strip().lower().replace(" ", "-")
        result = await self.db.execute(select(App).where(App.vendor_slug == vendor_slug))
        app = result.scalar_one_or_none()
        if not app:
            raise ValueError(f"App not found for vendor_slug '{vendor_slug}' — import apps first")

        license_ = License(
            app_id=app.id,
            license_type=LicenseType(row.get("license_type", "per_seat").lower()),
            seats_purchased=_safe_int(row.get("seats_purchased", "")),
            cost_per_seat_cents=_safe_int(row.get("cost_per_seat_cents", "")),
            total_annual_cost_cents=_safe_int(row.get("total_annual_cost_cents", "")),
            currency=row.get("currency", "USD").strip() or "USD",
            billing_cycle=row.get("billing_cycle") or None,
        )
        license_.recalculate_utilization()
        self.db.add(license_)
        await self.db.flush()
        return license_

    async def _import_contract_row(self, row: dict) -> Contract:
        vendor_slug = (row.get("vendor_slug") or row.get("app_name", "")).strip().lower().replace(" ", "-")
        result = await self.db.execute(select(App).where(App.vendor_slug == vendor_slug))
        app = result.scalar_one_or_none()
        if not app:
            raise ValueError(f"App not found for vendor_slug '{vendor_slug}'")

        contract = Contract(
            app_id=app.id,
            start_date=_parse_date(row.get("start_date", "")),
            end_date=_parse_date(row.get("end_date", "")),
            auto_renews=row.get("auto_renews", "").lower() in ("true", "yes", "1"),
            cancellation_notice_days=_safe_int(row.get("cancellation_notice_days", "")),
            total_value_cents=_safe_int(row.get("total_value_cents", "")),
            currency=row.get("currency", "USD").strip() or "USD",
            owner_email=row.get("owner_email") or None,
            notes=row.get("notes") or None,
        )
        self.db.add(contract)
        await self.db.flush()
        return contract
