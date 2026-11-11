"""
License reclamation: workflows (the rules) and items (one per person per app a rule flagged).

Both tables are new, so create_tables.py creates them automatically.

Item lifecycle
    open       flagged, waiting for a decision
    approved   an admin agreed the access should be removed (waiting for IT to remove it in Okta)
    reclaimed  was approved, and the next Okta sync no longer shows the assignment -> savings realized
    kept       the person still needs it; hidden until snooze_until, then reconsidered
    dismissed  ignore this person/app permanently
    closed     no longer relevant (the assignment disappeared, or the person became active again)
"""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class ReclamationWorkflow(Base):
    __tablename__ = "reclamation_workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))        # None = all apps
    user_emails: Mapped[list | None] = mapped_column(JSON)                      # None / empty = everyone assigned; else only these people
    inactivity_days: Mapped[int] = mapped_column(Integer, default=60)
    min_savings_cents: Mapped[int] = mapped_column(Integer, default=0)           # only flag paid seats worth at least this

    notify_slack: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_url_encrypted: Mapped[str | None] = mapped_column(Text)
    auto_run: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ask each person in Slack ("do you still need this?") before anything is reclaimed.
    ask_users_slack: Mapped[bool] = mapped_column(Boolean, default=False)
    ask_users_per_run: Mapped[int] = mapped_column(Integer, default=25)         # DMs sent per run, to avoid floods

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_summary: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReclamationItem(Base):
    __tablename__ = "reclamation_items"
    __table_args__ = (UniqueConstraint("workflow_id", "app_id", "user_id", name="uq_reclamation_item"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reclamation_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    days_inactive: Mapped[int | None] = mapped_column(Integer)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    est_annual_savings_cents: Mapped[int | None] = mapped_column(Integer)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # when the person was messaged in Slack

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReclamationSetting(Base):
    """Small key/value settings, e.g. the public address used in Slack button links."""
    __tablename__ = "reclamation_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)


class ReclamationAppTrust(Base):
    """Admin decision about how much to trust Okta sign-ins for one app.

    mode "trusted": people must sign in through Okta each time they use the app, so a missing sign-in
                    really means non-use. Counts in the analytics and workflows.
    mode "ignored": leave this app out of reclamation entirely.
    (No row = default: only counted if a connected vendor source reports real activity.)
    """
    __tablename__ = "reclamation_app_trust"

    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
