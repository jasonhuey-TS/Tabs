"""Per-app extras for the app screen: settings and notes, saved filters, change history, payments, documents,
sentiment, the HR roster, and per-day activity. All new tables, created automatically by create_tables.py."""
import uuid
from datetime import date, datetime
from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, func
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
    app_subcategory: Mapped[str | None] = mapped_column(String(120))   # e.g. "Accounting & Finance"
    app_functions: Mapped[list | None] = mapped_column(JSON)           # what the app is for, e.g. ["Expense Management"]; finer than the 12 categories, and an app can have several


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
    payment_type: Mapped[str] = mapped_column(String(16), default="ap")          # "ap" (accounts payable) or "expense"
    source: Mapped[str] = mapped_column(String(32), default="manual")           # manual | csv
    external_id: Mapped[str | None] = mapped_column(String(255))                # makes re-importing the same file safe
    import_batch: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppAlias(Base):
    """A vendor name from an upload that an admin matched to an app, so later uploads match automatically."""
    __tablename__ = "app_aliases"
    alias: Mapped[str] = mapped_column(String(255), primary_key=True)           # normalised vendor name
    app_id: Mapped[uuid.UUID] = _app_fk()


class AppIcon(Base):
    """An app's icon, fetched once by the server and kept. A failed lookup is remembered too, so a page of apps
    without icons doesn't re-try the internet every time it loads."""
    __tablename__ = "app_icons"
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    content_type: Mapped[str | None] = mapped_column(String(40))
    data: Mapped[bytes | None] = mapped_column(LargeBinary)
    source: Mapped[str | None] = mapped_column(String(20))                      # logo | favicon
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentFilter(Base):
    """A saved view of the Payments page."""
    __tablename__ = "payment_filters"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
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


class AppUserAttribute(Base):
    """Per-person values a vendor integration provides for one app (Zoom's meeting totals, account status, ...). One row per person per app."""
    __tablename__ = "app_user_attributes"
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)            # the connector key, e.g. "zoom"
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExternalLink(Base):
    """Which record in another system (Zylo) is which record in Tab, so a sync updates instead of duplicating.
    kind 'application': local_id is the Tab app. kind 'contract': local_id is the Tab contract (fingerprint = what was last synced)."""
    __tablename__ = "external_links"
    source: Mapped[str] = mapped_column(String(24), primary_key=True)                # e.g. "zylo"
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)                  # "application" | "contract"
    external_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    local_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), default="matched")               # matched | unmatched | ignored
    label: Mapped[str | None] = mapped_column(String(255))                           # the other system's name for it
    fingerprint: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DiscoveredApp(Base):
    """An app people have connected to their Google or Microsoft work account (found by asking Google and Microsoft who authorized what).
    status: new (not reviewed) | known (it is an app Tab already has) | added (added to Tab as shadow IT) | approved (added to Tab as sanctioned) | ignored."""
    __tablename__ = "discovered_apps"
    source: Mapped[str] = mapped_column(String(16), primary_key=True)                # "google" | "microsoft"
    external_id: Mapped[str] = mapped_column(String(255), primary_key=True)          # Google client id / Microsoft service principal id
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default="web")                     # web | native | third_party | internal
    scopes: Mapped[list | None] = mapped_column(JSON)
    risk: Mapped[str] = mapped_column(String(8), default="low")                      # low (sign-in only) | medium | high
    highlights: Mapped[list | None] = mapped_column(JSON)                            # what the access means, in plain words
    user_count: Mapped[int] = mapped_column(Integer, default=0)
    all_users: Mapped[bool] = mapped_column(Boolean, default=False)                  # an admin approved it for everyone (Microsoft)
    status: Mapped[str] = mapped_column(String(12), default="new", index=True)
    app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))            # the Tab app it is, once known or added
    active: Mapped[bool] = mapped_column(Boolean, default=True)                      # False once nobody has it authorized any more
    homepage: Mapped[str | None] = mapped_column(String(512))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiscoveredAppUser(Base):
    """Who authorized a discovered app (one row per person per app)."""
    __tablename__ = "discovered_app_users"
    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), primary_key=True)

