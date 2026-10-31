"""Repository for SFD personnel records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfd_bot.database.models import Personnel, utc_now


class PersonnelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_member(self, guild_id: int, discord_id: int) -> Personnel | None:
        result = await self._session.execute(
            select(Personnel).where(
                Personnel.guild_id == guild_id,
                Personnel.discord_id == discord_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_for_member(
        self,
        *,
        guild_id: int,
        discord_id: int,
        rank_key: str = "probationary_firefighter",
        division_key: str | None = None,
        status: str = "active",
    ) -> Personnel:
        record = Personnel(
            guild_id=guild_id,
            discord_id=discord_id,
            rank_key=rank_key,
            division_key=division_key,
            status=status,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def set_rank(
        self,
        *,
        guild_id: int,
        discord_id: int,
        rank_key: str,
    ) -> tuple[str | None, bool]:
        """Change a member's rank and return (old_rank, found)."""
        record = await self.get_for_member(guild_id, discord_id)
        if record is None:
            return None, False
        old_rank = record.rank_key
        record.rank_key = rank_key
        record.updated_at = utc_now()
        await self._session.flush()
        return old_rank, True

    async def list_active(self, guild_id: int, *, limit: int = 100) -> list[Personnel]:
        result = await self._session.execute(
            select(Personnel)
            .where(Personnel.guild_id == guild_id, Personnel.status == "active")
            .order_by(Personnel.rank_key, Personnel.discord_id)
            .limit(max(1, min(limit, 500)))
        )
        return list(result.scalars().all())
