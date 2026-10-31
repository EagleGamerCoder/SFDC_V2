"""Repository for auditable personnel rank changes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfd_bot.database.models import PromotionLog


class PromotionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_record(
        self,
        *,
        guild_id: int,
        actor_discord_id: int,
        target_discord_id: int,
        old_rank_key: str | None,
        new_rank_key: str,
        reason: str,
        outcome: str = "completed",
    ) -> PromotionLog:
        record = PromotionLog(
            guild_id=guild_id,
            actor_discord_id=actor_discord_id,
            target_discord_id=target_discord_id,
            old_rank_key=old_rank_key,
            new_rank_key=new_rank_key,
            reason=reason,
            outcome=outcome,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_for_member(
        self,
        *,
        guild_id: int,
        target_discord_id: int,
        limit: int = 25,
    ) -> list[PromotionLog]:
        result = await self._session.execute(
            select(PromotionLog)
            .where(
                PromotionLog.guild_id == guild_id,
                PromotionLog.target_discord_id == target_discord_id,
            )
            .order_by(PromotionLog.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        return list(result.scalars().all())
