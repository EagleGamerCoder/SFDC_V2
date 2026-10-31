"""Repository for verified Discord-to-Roblox account links."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfd_bot.database.models import UserLink, utc_now


class UserRepository:
    """Read and write account links without committing the surrounding transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_discord_id(self, discord_id: int) -> UserLink | None:
        result = await self._session.execute(
            select(UserLink).where(UserLink.discord_id == discord_id)
        )
        return result.scalar_one_or_none()

    async def get_by_roblox_user_id(self, roblox_user_id: int) -> UserLink | None:
        result = await self._session.execute(
            select(UserLink).where(UserLink.roblox_user_id == roblox_user_id)
        )
        return result.scalar_one_or_none()

    async def create_link(
        self,
        *,
        discord_id: int,
        roblox_user_id: int,
        roblox_username: str,
        verified_at: datetime | None = None,
    ) -> UserLink:
        """Create a new link. Unique constraints reject already-linked accounts."""
        link = UserLink(
            discord_id=discord_id,
            roblox_user_id=roblox_user_id,
            roblox_username=roblox_username,
            verified_at=verified_at or utc_now(),
        )
        self._session.add(link)
        await self._session.flush()
        return link

    async def update_roblox_username(self, discord_id: int, username: str) -> bool:
        """Update the cached Roblox username after a fresh successful lookup."""
        link = await self.get_by_discord_id(discord_id)
        if link is None:
            return False
        link.roblox_username = username
        link.updated_at = utc_now()
        await self._session.flush()
        return True

    async def unlink(self, discord_id: int) -> bool:
        """Remove a link. Dependent personnel records cascade according to the schema."""
        link = await self.get_by_discord_id(discord_id)
        if link is None:
            return False
        await self._session.delete(link)
        await self._session.flush()
        return True
