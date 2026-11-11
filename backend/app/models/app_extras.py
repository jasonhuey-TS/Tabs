"""Per-app extras for the app screen: settings and notes, saved filters, change history, payments, documents,
sentiment, the HR roster, and per-day activity. All new tables, created automatically by create_tables.py."""
import uuid
from datetime import date, datetime
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _app_fk(**kw):
    return mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True, **kw)


class AppSetting(Base):
    """One row per app: how 'active' is defined, free-form notes, and info the app record doesn't hold."""
    __tablename__ = "app_settings"
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    activity_threshold_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str | None] = mapped_column(Text)
    owner_email: Mapped[str | None] = mapped_column(String(255))
    business_owner: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    certifications: Mapped[list | None] = mapped_column(JSON)          # e.g. SOC 2, ISO 27001 (entered by hand)


class SavedFilter(Base):
    """A named combination of search / filters / activity bands. app_id None = available on every app."""
    __tablename__ = "saved_filters"
    id: Mapped[uuid.UUID] = _pk()
    app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppEvent(Base):
    """A line in an app's history: assignments added/removed, syncs, reclamation decisions, edits."""
    __tablename__ = "app_events"
    id: Mapped[uuid.UUID] = _pk()
    app_id: Mapped[uuid.UUID] = _app_fk()
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AppPayment(Base):
    __tablename__ = "app_payments"
    id: Mapped[uuid.UUID] = _pk()
    app_id: Mapped[uuid.UUID] = _app_fk()
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    reference: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppDocument(Base):
    __tablename__ = "app_documents"
    id: Mapped[uuid.UUID] = _pk()
    app_id: Mapped[uuid.UUID] = _app_fk()
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), default="other")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppFeedback(Base):
    __tablename__ = "app_feedback"
    id: Mapped[uuid.UUID] = _pk()
    app_id: Mapped[uuid.UUID] = _app_fk()
    rating: Mapped[int] = mapped_column(Integer, nullable=False)          # 1 (poor) .. 5 (great)
    person: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmployeeRoster(Base):
    """Emails from the HR system, uploaded by an admin; powers the 'In Employee Roster' column."""
    __tablename__ = "employee_roster"
    email: Mapped[str] = mapped_column(String(255), primary_key=True)


class UserActiveDay(Base):
    """One row per person per app per day with activity (an Okta sign-in, or Slack's daily active flag)."""
    __tablename__ = "user_active_days"
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    __table_args__ = (Index("ix_user_active_days_app_day", "app_id", "day"),)
