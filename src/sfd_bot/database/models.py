"""SQLAlchemy models for persistent SFD bot data.

All timestamps are stored as timezone-aware UTC datetimes by application code. SQLite
may return naive datetime objects for ``DateTime(timezone=True)`` columns; normalise those
at the boundary when calculating durations or reporting periods.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models, with stable constraint names for migrations."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class UserLink(Base):
    """A Discord account linked to a Roblox account after successful verification."""

    __tablename__ = "user_links"
    __table_args__ = (
        CheckConstraint("discord_id > 0", name="positive_discord_id"),
        CheckConstraint("roblox_user_id > 0", name="positive_roblox_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    roblox_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    roblox_username: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class VerificationSession(Base):
    """A short-lived Roblox profile-description challenge started by one Discord user.

    Only a hash of the challenge is stored. The raw challenge is shown privately to the
    user once and is never persisted in plaintext.
    """

    __tablename__ = "verification_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'expired', 'cancelled')",
            name="valid_status",
        ),
        CheckConstraint("attempt_count >= 0", name="nonnegative_attempt_count"),
        Index("ix_verification_sessions_discord_status", "discord_id", "status"),
        Index("ix_verification_sessions_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    roblox_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    roblox_username: Mapped[str] = mapped_column(String(32), nullable=False)
    challenge_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Personnel(Base):
    """SFD personnel data for a Discord guild."""

    __tablename__ = "personnel"
    __table_args__ = (
        UniqueConstraint("guild_id", "discord_id", name="personnel_guild_discord"),
        CheckConstraint("guild_id > 0", name="positive_guild_id"),
        CheckConstraint("status IN ('active', 'loa', 'suspended', 'inactive')", name="valid_status"),
        Index("ix_personnel_guild_status", "guild_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_links.discord_id", ondelete="CASCADE"),
        nullable=False,
    )
    rank_key: Mapped[str] = mapped_column(String(64), nullable=False, default="probationary_firefighter")
    division_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PromotionLog(Base):
    """Auditable record of a personnel rank change."""

    __tablename__ = "promotion_logs"
    __table_args__ = (
        CheckConstraint("guild_id > 0", name="positive_guild_id"),
        CheckConstraint("actor_discord_id > 0", name="positive_actor_id"),
        CheckConstraint("target_discord_id > 0", name="positive_target_id"),
        Index("ix_promotion_logs_guild_target", "guild_id", "target_discord_id"),
        Index("ix_promotion_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    old_rank_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_rank_key: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ShiftSession(Base):
    """A single on-duty session for a member of the fire department."""

    __tablename__ = "shift_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'admin_closed')", name="valid_status"),
        CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR "
            "(status IN ('completed', 'admin_closed') AND ended_at IS NOT NULL)",
            name="valid_end_time_for_status",
        ),
        Index("ix_shift_sessions_guild_started", "guild_id", "started_at"),
        Index("ix_shift_sessions_member_started", "guild_id", "discord_id", "started_at"),
        Index(
            "uq_shift_sessions_one_active_per_member",
            "guild_id",
            "discord_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    ended_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditEvent(Base):
    """Structured record of a supported Discord or SFD-specific event."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_guild_created", "guild_id", "created_at"),
        Index("ix_audit_events_guild_type", "guild_id", "event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Ticket(Base):
    """A support or personnel ticket created in the SFD Discord server."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'claimed', 'waiting', 'closed')",
            name="valid_status",
        ),
        Index("ix_tickets_guild_status", "guild_id", "status"),
        Index("ix_tickets_requester", "guild_id", "requester_discord_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    requester_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category_key: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PanelMessage(Base):
    """The Discord message used to display a persistent SFD panel."""

    __tablename__ = "panel_messages"
    __table_args__ = (UniqueConstraint("guild_id", "panel_key", name="panel_guild_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    panel_key: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class GuildSetting(Base):
    """A database-backed guild setting when JSON files are not suitable."""

    __tablename__ = "guild_settings"
    __table_args__ = (UniqueConstraint("guild_id", "key", name="guild_setting_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Qualification(Base):
    """A recorded qualification held by a department member."""

    __tablename__ = "qualifications"
    __table_args__ = (
        UniqueConstraint(
            "guild_id", "discord_id", "qualification_key", name="qualification_member_key"
        ),
        Index("ix_qualifications_guild_member", "guild_id", "discord_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    qualification_key: Mapped[str] = mapped_column(String(100), nullable=False)
    awarded_by_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class LeaveRequest(Base):
    """A member's leave-of-absence request."""

    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("requested_end > requested_start", name="end_after_start"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="valid_status"),
        Index("ix_leave_requests_guild_status", "guild_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewed_by_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Report(Base):
    """A structured report or staff concern submitted to the department."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_review', 'resolved', 'dismissed')",
            name="valid_status",
        ),
        Index("ix_reports_guild_status", "guild_id", "status"),
        Index("ix_reports_guild_created", "guild_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    category_key: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    assigned_to_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
