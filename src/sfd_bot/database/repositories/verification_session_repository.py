"""Repository for pending Roblox profile-description verification challenges."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sfd_bot.database.models import VerificationSession


class VerificationSessionRepository:
    """Manage verification challenge records inside the caller's transaction.

    The raw challenge must never be passed here; store only its SHA-256 hash. The service
    is responsible for generating the challenge and checking candidate values.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        discord_id: int,
        roblox_user_id: int,
        roblox_username: str,
        challenge_hash: str,
        expires_at: datetime,
    ) -> VerificationSession:
        """Cancel earlier pending challenges and create a fresh challenge."""
        await self.cancel_pending_for_discord(discord_id)
        session = VerificationSession(
            discord_id=discord_id,
            roblox_user_id=roblox_user_id,
            roblox_username=roblox_username,
            challenge_hash=challenge_hash,
            expires_at=expires_at,
            status="pending",
            attempt_count=0,
        )
        self._session.add(session)
        await self._session.flush()
        return session

    async def get_by_id(self, session_id: str) -> VerificationSession | None:
        result = await self._session.execute(
            select(VerificationSession).where(VerificationSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_active_for_discord(
        self,
        discord_id: int,
        *,
        now: datetime,
    ) -> VerificationSession | None:
        result = await self._session.execute(
            select(VerificationSession)
            .where(
                VerificationSession.discord_id == discord_id,
                VerificationSession.status == "pending",
                VerificationSession.expires_at > now,
            )
            .order_by(VerificationSession.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def increment_attempt(
        self,
        session_id: str,
        *,
        checked_at: datetime,
    ) -> bool:
        result = await self._session.execute(
            update(VerificationSession)
            .where(
                VerificationSession.id == session_id,
                VerificationSession.status == "pending",
            )
            .values(
                attempt_count=VerificationSession.attempt_count + 1,
                last_checked_at=checked_at,
            )
            .returning(VerificationSession.id)
        )

        await self._session.flush()

        return result.scalar_one_or_none() is not None

    async def mark_completed(
        self,
        session_id: str,
        *,
        completed_at: datetime,
    ) -> bool:
        result = await self._session.execute(
            update(VerificationSession)
            .where(
                VerificationSession.id == session_id,
                VerificationSession.status == "pending",
                VerificationSession.expires_at > completed_at,
            )
            .values(
                status="completed",
                completed_at=completed_at,
                last_checked_at=completed_at,
            )
            .returning(VerificationSession.id)
        )

        await self._session.flush()

        return result.scalar_one_or_none() is not None

    async def expire_pending(self, *, now: datetime) -> int:
        result = await self._session.execute(
            update(VerificationSession)
            .where(
                VerificationSession.status == "pending",
                VerificationSession.expires_at <= now,
            )
            .values(status="expired")
            .returning(VerificationSession.id)
        )

        await self._session.flush()

        return len(result.scalars().all())

    async def cancel_pending_for_discord(
        self,
        discord_id: int,
    ) -> int:
        result = await self._session.execute(
            update(VerificationSession)
            .where(
                VerificationSession.discord_id == discord_id,
                VerificationSession.status == "pending",
            )
            .values(status="cancelled")
            .returning(VerificationSession.id)
        )

        await self._session.flush()

        return len(result.scalars().all())