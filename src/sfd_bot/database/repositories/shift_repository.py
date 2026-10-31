"""Repository for shift sessions and reporting-period queries."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfd_bot.database.models import ShiftSession, utc_now


class ShiftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, *, guild_id: int, discord_id: int) -> ShiftSession | None:
        result = await self._session.execute(
            select(ShiftSession).where(
                ShiftSession.guild_id == guild_id,
                ShiftSession.discord_id == discord_id,
                ShiftSession.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def start(
        self,
        *,
        guild_id: int,
        discord_id: int,
        started_at: datetime | None = None,
    ) -> ShiftSession:
        """Create an active shift; the database prevents a second active shift per member."""
        session = ShiftSession(
            guild_id=guild_id,
            discord_id=discord_id,
            started_at=started_at or utc_now(),
            status="active",
        )
        self._session.add(session)
        await self._session.flush()
        return session

    async def end(
        self,
        *,
        guild_id: int,
        discord_id: int,
        ended_by: int,
        admin_closed: bool = False,
        reason: str | None = None,
        ended_at: datetime | None = None,
    ) -> ShiftSession | None:
        session = await self.get_active(guild_id=guild_id, discord_id=discord_id)
        if session is None:
            return None
        closing_time = ended_at or utc_now()
        if closing_time.tzinfo is None:
            closing_time = closing_time.replace(tzinfo=timezone.utc)
        else:
            closing_time = closing_time.astimezone(timezone.utc)

        started_at = session.started_at
        if started_at.tzinfo is None:
            # SQLite does not preserve timezone metadata for DateTime columns.
            started_at = started_at.replace(tzinfo=timezone.utc)
        else:
            started_at = started_at.astimezone(timezone.utc)
        if closing_time < started_at:
            raise ValueError("A shift cannot end before it starts.")
        session.ended_at = closing_time
        session.ended_by = ended_by
        session.end_reason = reason
        session.status = "admin_closed" if admin_closed else "completed"
        await self._session.flush()
        return session

    async def list_overlapping_period(
        self,
        *,
        guild_id: int,
        period_start: datetime,
        period_end: datetime,
        discord_id: int | None = None,
        limit: int = 1000,
    ) -> list[ShiftSession]:
        """Return sessions intersecting a reporting period; split durations in the service."""
        criteria = [
            ShiftSession.guild_id == guild_id,
            ShiftSession.started_at < period_end,
            or_(ShiftSession.ended_at.is_(None), ShiftSession.ended_at > period_start),
        ]
        if discord_id is not None:
            criteria.append(ShiftSession.discord_id == discord_id)
        result = await self._session.execute(
            select(ShiftSession)
            .where(and_(*criteria))
            .order_by(ShiftSession.started_at)
            .limit(max(1, min(limit, 10000)))
        )
        return list(result.scalars().all())
