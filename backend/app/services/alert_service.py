"""
Alert service — creates and fires renewal alerts for contracts nearing expiry.
"""
import httpx
import structlog
from datetime import datetime, timezone, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Contract, RenewalAlert, ContractStatus, AlertStatus
from app.core.config import settings

log = structlog.get_logger()


class AlertService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def schedule_alerts_for_contract(self, contract: Contract) -> list[RenewalAlert]:
        """Create pending alert records for a new/updated contract."""
        if not contract.end_date:
            return []

        alerts = []
        for days in settings.RENEWAL_ALERT_DAYS:
            fire_date = contract.end_date - timedelta(days=days)
            # Don't create alerts for dates already in the past
            if fire_date < date.today():
                continue
            alert = RenewalAlert(
                contract_id=contract.id,
                days_before_expiry=days,
                scheduled_for=datetime.combine(fire_date, datetime.min.time()).replace(tzinfo=timezone.utc),
            )
            self.db.add(alert)
            alerts.append(alert)

        await self.db.flush()
        return alerts

    async def check_and_send_alerts(self) -> int:
        """Find due alerts and dispatch them. Returns count of alerts sent."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(RenewalAlert)
            .where(
                RenewalAlert.status == AlertStatus.PENDING,
                RenewalAlert.scheduled_for <= now,
            )
            .options(selectinload(RenewalAlert.contract).selectinload(Contract.app))
        )
        alerts = result.scalars().all()
        sent = 0

        for alert in alerts:
            try:
                await self._send_alert(alert)
                alert.status = AlertStatus.SENT
                alert.sent_at = now
                sent += 1
            except Exception as exc:
                log.error("alert.send_failed", alert_id=str(alert.id), error=str(exc))

        await self.db.flush()
        return sent

    async def _send_alert(self, alert: RenewalAlert) -> None:
        contract = alert.contract
        app = contract.app
        owner = contract.owner_email

        message = (
            f"⚠️ *Renewal alert:* *{app.name}* contract expires in "
            f"*{alert.days_before_expiry} days* ({contract.end_date}). "
            f"Owner: {owner or 'unassigned'}"
        )

        tasks = []
        if settings.SLACK_WEBHOOK_URL:
            await self._send_slack(message)
            alert.sent_via = "slack"

        if owner and settings.SMTP_HOST:
            await self._send_email(owner, app.name, contract, alert)
            alert.sent_via = (alert.sent_via or "") + ",email"

        alert.sent_to = owner

    async def _send_slack(self, message: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(settings.SLACK_WEBHOOK_URL, json={"text": message}, timeout=10)
            resp.raise_for_status()

    async def _send_email(self, to: str, app_name: str, contract: Contract, alert: RenewalAlert) -> None:
        # Placeholder — swap in your SMTP lib (aiosmtplib, SendGrid, etc.)
        log.info("alert.email.send", to=to, app=app_name, days=alert.days_before_expiry)
